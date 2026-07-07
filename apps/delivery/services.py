"""
Services for delivery app.
Business logic for delivery zones, assignments, and status tracking.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Delivery, DeliveryZone


# =============================================================================
# Delivery Zone Services
# =============================================================================

def get_delivery_zones():
    """Get all active delivery zones."""
    return DeliveryZone.objects.filter(is_active=True).order_by('name')


def get_zone_for_address(address) -> DeliveryZone:
    """Get the delivery zone for an address based on ward number."""
    for zone in DeliveryZone.objects.filter(is_active=True):
        if address.ward_number in (zone.ward_numbers or []):
            return zone
    return None


def calculate_delivery_estimate(ward_number: int) -> dict:
    """Calculate delivery time and fee for a ward number."""
    zone = None
    for z in DeliveryZone.objects.filter(is_active=True):
        if ward_number in (z.ward_numbers or []):
            zone = z
            break
    
    if zone:
        return {
            'available': True,
            'zone_name': zone.name,
            'fee': zone.base_delivery_fee,
            'estimated_minutes': zone.estimated_delivery_time_minutes,
        }
    
    return {
        'available': False,
        'message': 'Delivery not available to this location yet.'
    }


# =============================================================================
# Delivery Assignment Services
# =============================================================================

def get_available_deliveries(zone=None):
    """Get unassigned deliveries, optionally filtered by zone."""
    queryset = Delivery.objects.filter(status='unassigned').select_related(
        'order', 'order__customer', 'order__delivery_address'
    )
    
    if zone:
        queryset = queryset.filter(
            order__delivery_address__ward_number__in=zone.ward_numbers
        )
    
    return queryset.order_by('order__placed_at')


def assign_delivery(delivery_id: int, rider_id: int) -> tuple:
    """
    Assign a delivery to a rider.
    Returns (success, error_message)
    """
    from apps.accounts.models import RiderProfile
    
    try:
        delivery = Delivery.objects.get(id=delivery_id, status='unassigned')
    except Delivery.DoesNotExist:
        return False, "Delivery not found or already assigned"
    
    try:
        rider = RiderProfile.objects.get(id=rider_id, is_available=True)
    except RiderProfile.DoesNotExist:
        return False, "Rider not found or not available"
    
    if not rider.can_accept_deliveries:
        return False, f"Cannot assign: rider is not KYC verified (Status: {rider.get_kyc_status_display()})."
    
    # Calculate delivery fee for rider
    delivery_fee = calculate_delivery_fee_for_rider(delivery)
    
    with transaction.atomic():
        delivery.rider = rider
        delivery.status = Delivery.Status.ASSIGNED
        delivery.assigned_at = timezone.now()
        delivery.delivery_fee_owed_to_rider = delivery_fee
        delivery.save()
    
    return True, None


def calculate_delivery_fee_for_rider(delivery: Delivery) -> float:
    """
    Calculate fee owed to rider for a delivery.
    Base fee minus platform commission.
    """
    from decimal import Decimal
    
    # Base fee calculation
    base_fee = delivery.order.delivery_fee
    
    # Rider gets 80% of delivery fee
    rider_share = base_fee * Decimal('0.80')
    
    return rider_share


def unassign_delivery(delivery_id: int) -> bool:
    """Unassign a delivery, returning it to unassigned pool."""
    try:
        delivery = Delivery.objects.get(id=delivery_id, status='assigned')
        delivery.rider = None
        delivery.status = Delivery.Status.UNASSIGNED
        delivery.assigned_at = None
        delivery.delivery_fee_owed_to_rider = 0
        delivery.save()
        return True
    except Delivery.DoesNotExist:
        return False


# =============================================================================
# Delivery Status Services
# =============================================================================

def update_delivery_status(delivery_id: int, new_status: str, 
                          failure_reason: str = None, rider=None) -> tuple:
    """
    Update delivery status with validation.
    Returns (success, error_message)
    """
    try:
        delivery = Delivery.objects.get(id=delivery_id)
    except Delivery.DoesNotExist:
        return False, "Delivery not found"
    
    # Validate status transition
    valid_transitions = {
        Delivery.Status.UNASSIGNED: [Delivery.Status.ASSIGNED],
        Delivery.Status.ASSIGNED: [Delivery.Status.PICKED_UP, Delivery.Status.FAILED],
        Delivery.Status.PICKED_UP: [Delivery.Status.DELIVERED, Delivery.Status.FAILED],
        Delivery.Status.DELIVERED: [],
        Delivery.Status.FAILED: [],
    }
    
    if new_status not in valid_transitions.get(delivery.status, []):
        return False, f"Invalid status transition from {delivery.status} to {new_status}"
    
    with transaction.atomic():
        delivery.status = new_status
        
        if new_status == Delivery.Status.PICKED_UP:
            delivery.picked_up_at = timezone.now()
        elif new_status == Delivery.Status.DELIVERED:
            delivery.delivered_at = timezone.now()
            
            # Update order status
            delivery.order.status = 'out_for_delivery'
            delivery.order.save(update_fields=['status'])
            
            # Refresh rider stats
            if delivery.rider:
                from apps.accounts.services import refresh_rider_stats
                refresh_rider_stats(delivery.rider)
        elif new_status == Delivery.Status.FAILED:
            delivery.failure_reason = failure_reason or ''
        
        delivery.save()
    
    return True, None


@transaction.atomic
def complete_delivery(delivery_id: int, rider=None) -> tuple:
    """
    Mark delivery as completed.
    Updates order status and handles COD payment if applicable.
    """
    try:
        delivery = Delivery.objects.get(id=delivery_id)
    except Delivery.DoesNotExist:
        return False, "Delivery not found"
    
    if delivery.status not in [Delivery.Status.ASSIGNED, Delivery.Status.PICKED_UP]:
        return False, f"Cannot complete delivery in {delivery.status} status"
    
    with transaction.atomic():
        delivery.status = Delivery.Status.DELIVERED
        delivery.delivered_at = timezone.now()
        delivery.save()
        
        # Check if all deliveries for the order are complete
        order = delivery.order
        # Use the correct related_name from Delivery.order
        all_delivered = not Delivery.objects.filter(
            order=order
        ).exclude(status=Delivery.Status.DELIVERED).exists()
        
        if all_delivered:
            order.status = 'delivered'
            order.delivered_at = timezone.now()
            
            # Handle COD payment
            if order.payment_method == 'cod' and order.payment_status == 'pending':
                from apps.orders.models import Transaction
                order.payment_status = 'paid'
                
                Transaction.objects.create(
                    order=order,
                    gateway='cod',
                    amount=order.total_amount,
                    status='success'
                )
            
            order.save(update_fields=['status', 'delivered_at', 'payment_status'])
        
        # Refresh rider stats
        if delivery.rider:
            from apps.accounts.services import refresh_rider_stats
            refresh_rider_stats(delivery.rider)
    
    return True, None


# =============================================================================
# Rider Delivery Management
# =============================================================================

def get_rider_active_deliveries(rider):
    """Get rider's currently active deliveries."""
    return Delivery.objects.filter(
        rider=rider,
        status__in=[Delivery.Status.ASSIGNED, Delivery.Status.PICKED_UP]
    ).select_related(
        'order', 'order__customer', 'order__delivery_address'
    )


def get_rider_delivery_history(rider, limit: int = 50) -> list:
    """Get rider's delivery history."""
    return Delivery.objects.filter(
        rider=rider
    ).select_related(
        'order', 'order__customer'
    ).order_by('-assigned_at')[:limit]


def accept_delivery(rider, delivery_id: int) -> tuple:
    """
    Rider accepts an available delivery.
    """
    if not rider.can_accept_deliveries:
        return False, f"KYC verification required ({rider.get_kyc_status_display()}). Complete KYC verification to accept delivery tasks."

    try:
        delivery = Delivery.objects.get(id=delivery_id, status='unassigned')
    except Delivery.DoesNotExist:
        return False, "Delivery not found or already taken"
    
    # Calculate fee
    fee = calculate_delivery_fee_for_rider(delivery)
    
    with transaction.atomic():
        delivery.rider = rider
        delivery.status = Delivery.Status.ASSIGNED
        delivery.assigned_at = timezone.now()
        delivery.delivery_fee_owed_to_rider = fee
        delivery.save()
    
    return True, None


def reject_delivery(rider, delivery_id: int) -> bool:
    """Rider rejects an assigned delivery (admin reassigns)."""
    return unassign_delivery(delivery_id)


# =============================================================================
# Delivery Analytics
# =============================================================================

def get_delivery_stats(zone=None) -> dict:
    """Get delivery statistics."""
    queryset = Delivery.objects.all()
    
    if zone:
        queryset = queryset.filter(
            order__delivery_address__ward_number__in=zone.ward_numbers
        )
    
    total = queryset.count()
    delivered = queryset.filter(status='delivered').count()
    failed = queryset.filter(status='failed').count()
    in_progress = queryset.filter(
        status__in=['assigned', 'picked_up']
    ).count()
    
    avg_time = None
    delivered_qs = queryset.filter(status='delivered', delivered_at__isnull=False)
    if delivered_qs.exists():
        from django.db.models import Avg
        avg = delivered_qs.aggregate(
            avg_time=Avg(
                F('delivered_at') - F('assigned_at')
            )
        )['avg_time']
        if avg:
            avg_time = avg.total_seconds() / 60  # Convert to minutes
    
    return {
        'total': total,
        'delivered': delivered,
        'failed': failed,
        'in_progress': in_progress,
        'unassigned': queryset.filter(status='unassigned').count(),
        'success_rate': (delivered / total * 100) if total > 0 else 0,
        'average_delivery_time_minutes': avg_time,
    }