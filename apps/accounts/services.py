"""
Services for accounts app.
Contains business logic for user management, OTP, vendor/rider stats, and notifications.
"""
import random
import re
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from .models import Address, RiderProfile, User, VendorProfile

UserModel = get_user_model()


# =============================================================================
# OTP Services
# =============================================================================

def generate_otp(user: User) -> str:
    """
    Generate a 6-digit OTP and store it in cache with expiry.
    Returns the OTP code.
    """
    otp = str(random.randint(100000, 999999))
    cache_key = f"otp:{user.id}"
    
    # Store OTP with 10 minute expiry
    cache.set(cache_key, {
        'code': otp,
        'attempts': 0,
        'created_at': timezone.now().isoformat()
    }, timeout=settings.OTP_EXPIRY_MINUTES * 60)
    
    return otp


def verify_otp_code(user: User, code: str) -> bool:
    """
    Verify the OTP code against the cached value.
    Returns True if valid, False otherwise.
    Increments attempt counter and invalidates after max attempts.
    """
    cache_key = f"otp:{user.id}"
    cached_data = cache.get(cache_key)
    
    if not cached_data:
        return False
    
    max_attempts = settings.OTP_MAX_ATTEMPTS
    
    # Increment attempt counter
    cached_data['attempts'] = cached_data.get('attempts', 0) + 1
    
    if cached_data['attempts'] > max_attempts:
        cache.delete(cache_key)
        return False
    
    if cached_data['code'] == code:
        cache.delete(cache_key)
        return True
    
    # Update cache with new attempt count
    cache.set(cache_key, cached_data, timeout=settings.OTP_EXPIRY_MINUTES * 60)
    return False


def send_otp_sms(phone_number: str, otp: str) -> bool:
    """
    Send OTP via SMS gateway (Sparrow SMS or similar).
    Returns True if sent successfully.
    """
    # Placeholder - implement with actual SMS gateway
    sms_gateway_url = getattr(settings, 'SMS_GATEWAY_URL', '')
    sms_api_key = getattr(settings, 'SMS_API_KEY', '')
    
    if not sms_gateway_url or not sms_api_key:
        # Log for development
        print(f"[SMS] Sending OTP {otp} to {phone_number}")
        return True
    
    # Implement actual SMS sending here
    # Example with Sparrow SMS:
    # import requests
    # response = requests.post(sms_gateway_url, json={
    #     'key': sms_api_key,
    #     'to': phone_number,
    #     'message': f"Your Makwanpur Mart OTP is: {otp}"
    # })
    # return response.status_code == 200
    
    return True


def resend_otp(user: User) -> str:
    """
    Invalidate existing OTP and generate a new one.
    Returns the new OTP.
    """
    cache_key = f"otp:{user.id}"
    cache.delete(cache_key)
    return generate_otp(user)


# =============================================================================
# Vendor Services
# =============================================================================

def refresh_vendor_stats(vendor: VendorProfile) -> None:
    """
    Recalculate and update denormalized vendor stats:
    - average_rating: from delivered orders' reviews
    - total_sales: count of delivered order items
    
    Called on review creation and order delivery.
    """
    from apps.catalog.models import Review
    from apps.orders.models import OrderItem
    
    # Calculate average rating from reviews
    reviews = Review.objects.filter(
        product__vendor=vendor,
        product__is_active=True
    ).aggregate(avg_rating=Avg('rating'))
    
    avg_rating = reviews['avg_rating'] or 0
    
    # Count total delivered sales
    total_sales = OrderItem.objects.filter(
        vendor=vendor,
        item_status='delivered'
    ).count()
    
    # Update vendor profile
    VendorProfile.objects.filter(pk=vendor.pk).update(
        average_rating=avg_rating,
        total_sales=total_sales
    )


def get_vendor_dashboard_stats(vendor: VendorProfile) -> dict:
    """
    Get comprehensive stats for vendor dashboard.
    """
    from apps.catalog.models import Product
    from apps.orders.models import OrderItem
    
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    # Today's orders
    today_orders = OrderItem.objects.filter(
        vendor=vendor,
        order__placed_at__date=today
    ).count()
    
    # This month's revenue
    month_revenue = OrderItem.objects.filter(
        vendor=vendor,
        item_status='delivered',
        order__placed_at__date__gte=month_start
    ).aggregate(total=Sum('unit_price'))['total'] or 0
    
    # Pending orders
    pending_orders = OrderItem.objects.filter(
        vendor=vendor,
        item_status__in=['pending', 'confirmed', 'preparing']
    ).count()
    
    # Low stock products
    low_stock = Product.objects.filter(
        vendor=vendor,
        is_active=True
    ).filter(
        Q(stock_quantity__lte=5) | 
        Q(variants__stock_quantity__lte=5)
    ).distinct().count()
    
    return {
        'total_products': Product.objects.filter(vendor=vendor, is_active=True).count(),
        'today_orders': today_orders,
        'month_revenue': month_revenue,
        'pending_orders': pending_orders,
        'low_stock_count': low_stock,
        'average_rating': vendor.average_rating,
        'total_sales': vendor.total_sales,
    }


# =============================================================================
# Rider Services
# =============================================================================

def refresh_rider_stats(rider: RiderProfile) -> None:
    """
    Update denormalized rider stats.
    """
    RiderProfile.objects.filter(pk=rider.pk).update(
        total_deliveries=rider.deliveries.filter(
            status='delivered'
        ).count()
    )


def get_available_deliveries(rider: RiderProfile) -> list:
    """
    Get unassigned deliveries in the rider's zone.
    """
    from apps.delivery.models import Delivery
    
    if not rider.current_zone:
        return []
    
    return Delivery.objects.filter(
        status='unassigned',
        order__delivery_address__municipality__in=rider.current_zone.ward_numbers
    ).select_related(
        'order', 'order__customer', 'order__delivery_address'
    ).order_by('order__placed_at')


def accept_delivery(rider: RiderProfile, delivery_id: int) -> bool:
    """
    Accept a delivery assignment.
    """
    from apps.delivery.models import Delivery
    
    try:
        delivery = Delivery.objects.get(id=delivery_id, status='unassigned')
        
        delivery.rider = rider
        delivery.status = Delivery.Status.ASSIGNED
        delivery.assigned_at = timezone.now()
        delivery.save()
        
        return True
    except Delivery.DoesNotExist:
        return False


def update_delivery_status(delivery_id: int, new_status: str, failure_reason: str = None) -> bool:
    """
    Update delivery status with proper state transitions.
    """
    from apps.delivery.models import Delivery
    
    valid_transitions = {
        'unassigned': ['assigned'],
        'assigned': ['picked_up', 'failed'],
        'picked_up': ['delivered', 'failed'],
        'delivered': [],
        'failed': [],
    }
    
    try:
        delivery = Delivery.objects.get(id=delivery_id)
        
        if new_status not in valid_transitions.get(delivery.status, []):
            return False
        
        delivery.status = new_status
        
        if new_status == 'picked_up':
            delivery.picked_up_at = timezone.now()
        elif new_status == 'delivered':
            delivery.delivered_at = timezone.now()
        elif new_status == 'failed':
            delivery.failure_reason = failure_reason or ''
        
        delivery.save()
        
        # Refresh rider stats if delivered
        if new_status == 'delivered' and delivery.rider:
            refresh_rider_stats(delivery.rider)
        
        return True
    except Delivery.DoesNotExist:
        return False


# =============================================================================
# Address Services
# =============================================================================

def get_default_address(user: User) -> Address:
    """
    Get user's default address or first available.
    """
    return Address.objects.filter(user=user, is_default=True).first() or \
           Address.objects.filter(user=user).first()


def validate_delivery_zone(address: Address) -> dict:
    """
    Check if address is within delivery zones.
    Returns zone info if deliverable, None otherwise.
    """
    from apps.delivery.models import DeliveryZone
    
    zone = None
    for z in DeliveryZone.objects.filter(is_active=True):
        if address.ward_number in (z.ward_numbers or []):
            zone = z
            break
    
    if zone:
        return {
            'deliverable': True,
            'zone': zone.name,
            'fee': zone.base_delivery_fee,
            'estimated_time': zone.estimated_delivery_time_minutes
        }
    
    return {
        'deliverable': False,
        'message': 'Delivery not available in your area yet.'
    }


# =============================================================================
# User Services
# =============================================================================

def get_user_by_email(email: str) -> User:
    """
    Get user by email (case-insensitive).
    """
    return User.objects.get(email__iexact=email)


def check_email_exists(email: str) -> bool:
    """Check if email is already registered."""
    return User.objects.filter(email__iexact=email).exists()


def check_phone_exists(phone: str) -> bool:
    """Check if phone number is already registered."""
    return User.objects.filter(phone_number=phone).exists()


def normalize_nepali_phone(phone: str) -> str:
    """
    Normalize Nepali phone number to +977 format.
    """
    # Remove spaces, dashes
    phone = re.sub(r'[\s\-]', '', phone)
    
    if not phone.startswith('+'):
        if phone.startswith('0'):
            phone = '+977' + phone[1:]
        elif phone.startswith('97'):
            phone = '+' + phone
        else:
            phone = '+977' + phone
    
    return phone


# =============================================================================
# Registration Services
# =============================================================================

def register_customer(email: str, username: str, phone: str, password: str) -> User:
    """
    Create a new customer account.
    """
    normalized_phone = normalize_nepali_phone(phone)
    
    user = User.objects.create_user(
        email=email.lower(),
        username=username,
        phone_number=normalized_phone,
        password=password,
        role=User.Role.CUSTOMER
    )
    
    return user


def register_vendor(user: User, shop_name: str, shop_slug: str, category_id: int, 
                    payout_method: str, payout_details: str) -> VendorProfile:
    """
    Create vendor profile for existing user.
    """
    from apps.catalog.models import Category
    
    category = Category.objects.get(id=category_id)
    
    vendor = VendorProfile.objects.create(
        user=user,
        shop_name=shop_name,
        shop_slug=shop_slug,
        category=category,
        payout_method=payout_method,
        payout_account_details=payout_details,
        verification_status=VendorProfile.VerificationStatus.PENDING
    )
    
    # Update user role
    user.role = User.Role.VENDOR
    user.save(update_fields=['role'])
    
    return vendor


def register_rider(user: User, vehicle_type: str) -> RiderProfile:
    """
    Create rider profile for existing user.
    """
    rider = RiderProfile.objects.create(
        user=user,
        vehicle_type=vehicle_type,
        is_available=False
    )
    
    user.role = User.Role.RIDER
    user.save(update_fields=['role'])
    
    return rider