"""
Services for support app.
Business logic for complaints, notifications, and audit logging.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import AuditLog, GrievanceComplaint, Notification

UserModel = get_user_model()


# =============================================================================
# Complaint Services
# =============================================================================

def create_complaint(order, user, category: str, description: str) -> GrievanceComplaint:
    """Create a new grievance complaint."""
    complaint = GrievanceComplaint.objects.create(
        order=order,
        raised_by=user,
        category=category,
        description=description,
        status=GrievanceComplaint.Status.OPEN
    )
    
    # Create audit log
    audit("complaint_created", "GrievanceComplaint", complaint.id, user)
    
    # Send notification to admin
    send_notification_to_admins(
        title="New Grievance Complaint",
        message=f"Complaint #{complaint.id} filed by {user.email} regarding order #{order.order_number}",
        complaint_type=category
    )
    
    return complaint


def update_complaint_status(complaint: GrievanceComplaint, new_status: str, 
                           notes: str = None, updated_by=None) -> GrievanceComplaint:
    """Update complaint status and optionally add resolution notes."""
    complaint.status = new_status
    
    if notes:
        complaint.resolution_notes = notes
    
    if new_status == GrievanceComplaint.Status.RESOLVED:
        complaint.resolved_at = timezone.now()
    
    complaint.save(update_fields=['status', 'resolution_notes', 'resolved_at'])
    
    # Audit log
    audit("complaint_status_updated", "GrievanceComplaint", complaint.id, updated_by,
          extra=f"New status: {new_status}")
    
    # Notify user
    send_notification(
        complaint.raised_by,
        Notification.Type.SYSTEM,
        f"Complaint #{complaint.id} - Status Update",
        f"Your complaint has been {new_status.replace('_', ' ')}.",
        Notification.Channel.IN_APP
    )
    
    return complaint


def get_user_complaints(user) -> list:
    """Get all complaints filed by a user."""
    return GrievanceComplaint.objects.filter(
        raised_by=user
    ).select_related('order').order_by('-created_at')


def get_pending_complaints() -> list:
    """Get all open and in-review complaints."""
    return GrievanceComplaint.objects.filter(
        status__in=[GrievanceComplaint.Status.OPEN, GrievanceComplaint.Status.IN_REVIEW]
    ).select_related('order', 'raised_by').order_by('-created_at')


# =============================================================================
# Notification Services
# =============================================================================

def send_notification(user, notification_type: str, title: str, message: str, 
                      channel: str = Notification.Channel.SMS) -> Notification:
    """Send notification to a user."""
    notification = Notification.objects.create(
        user=user,
        type=notification_type,
        title=title,
        message=message,
        sent_via=channel
    )
    
    # In production, queue SMS/Push via Celery
    # send_sms_task.delay(user.phone_number, message)
    
    return notification


def send_notification_to_admins(title: str, message: str, complaint_type: str = None):
    """Send notification to all admin users."""
    admins = UserModel.objects.filter(role=UserModel.Role.ADMIN, is_active=True)
    
    for admin in admins:
        send_notification(
            admin,
            Notification.Type.SYSTEM,
            title,
            message,
            Notification.Channel.IN_APP
        )


def get_user_notifications(user, unread_only: bool = False) -> list:
    """Get notifications for a user."""
    queryset = Notification.objects.filter(user=user)
    
    if unread_only:
        queryset = queryset.filter(is_read=False)
    
    return queryset.order_by('-created_at')


def mark_notification_read(notification_id: int, user) -> bool:
    """Mark a notification as read."""
    try:
        notification = Notification.objects.get(id=notification_id, user=user)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return True
    except Notification.DoesNotExist:
        return False


def mark_all_notifications_read(user) -> int:
    """Mark all notifications as read for a user."""
    count = Notification.objects.filter(user=user, is_read=False).update(is_read=True)
    return count


def get_unread_notification_count(user) -> int:
    """Get count of unread notifications."""
    return Notification.objects.filter(user=user, is_read=False).count()


# =============================================================================
# Audit Log Services
# =============================================================================

def audit(action: str, model_affected: str, object_id: int, user=None, 
          ip_address: str = None, extra: str = None) -> AuditLog:
    """
    Create an audit log entry.
    
    Args:
        action: Description of the action (e.g., "complaint_created", "vendor_approved")
        model_affected: Model name (e.g., "GrievanceComplaint", "VendorProfile")
        object_id: Primary key of the affected object
        user: User performing the action (None for system actions)
        ip_address: IP address of the request
        extra: Additional context information
    """
    log_message = action
    if extra:
        log_message = f"{action} | {extra}"
    
    return AuditLog.objects.create(
        user=user,
        action=log_message,
        model_affected=model_affected,
        object_id=str(object_id),
        ip_address=ip_address
    )


def get_model_audit_trail(model_affected: str, object_id: int) -> list:
    """Get audit trail for a specific model instance."""
    return AuditLog.objects.filter(
        model_affected=model_affected,
        object_id=str(object_id)
    ).select_related('user').order_by('-timestamp')


def get_user_audit_trail(user) -> list:
    """Get all actions performed by a specific user."""
    return AuditLog.objects.filter(
        user=user
    ).order_by('-timestamp')


# =============================================================================
# Help Center Services
# =============================================================================

def get_faq_categories() -> dict:
    """Get FAQ categories with questions."""
    return {
        'orders': [
            {
                'question': 'How do I track my order?',
                'answer': 'You can track your order by visiting the "My Orders" section of your account. Each order has a tracking timeline showing the current status.'
            },
            {
                'question': 'Can I cancel my order?',
                'answer': 'Yes, you can cancel your order if it has not yet been prepared. Go to the order details page and click "Cancel Order".'
            },
            {
                'question': 'What payment methods are accepted?',
                'answer': 'We accept eSewa, Khalti, and Cash on Delivery (COD).'
            },
        ],
        'delivery': [
            {
                'question': 'How long does delivery take?',
                'answer': 'Delivery time depends on your ward. Typically, deliveries within Hetauda take 30-60 minutes.'
            },
            {
                'question': 'What are the delivery charges?',
                'answer': 'Delivery charges vary by ward. You can see the exact fee at checkout based on your delivery address.'
            },
        ],
        'returns': [
            {
                'question': 'How do I request a return?',
                'answer': 'Visit the order details page for delivered orders and click "Request Return". Fill out the return form with your reason.'
            },
            {
                'question': 'How long does the refund process take?',
                'answer': 'Refunds are processed within 5-7 business days after we receive the returned item.'
            },
        ],
        'vendor': [
            {
                'question': 'How do I become a vendor?',
                'answer': 'Go to the vendor registration page, fill out the form, and agree to the vendor terms. Your application will be reviewed within 2-3 business days.'
            },
            {
                'question': 'When do I receive my payouts?',
                'answer': 'Vendor payouts are processed weekly for delivered orders.'
            },
        ],
    }


def create_support_ticket(user, subject: str, description: str, priority: str = 'normal') -> dict:
    """
    Create a support ticket (simplified - in production would integrate with ticketing system).
    """
    # For demo, create a complaint record
    from apps.orders.models import Order
    
    # Find most recent order as context
    last_order = Order.objects.filter(customer=user).first()
    
    if last_order:
        complaint = create_complaint(
            order=last_order,
            user=user,
            category=GrievanceComplaint.Category.OTHER,
            description=f"[Support Ticket: {priority.upper()}] {subject}\n\n{description}"
        )
        return {'ticket_id': complaint.id, 'status': 'created'}
    
    return {'ticket_id': None, 'status': 'error', 'message': 'No order found to associate ticket with'}