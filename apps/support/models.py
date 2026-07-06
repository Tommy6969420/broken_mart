"""
Trust, support & compliance: GrievanceComplaint, Notification, AuditLog.

GrievanceComplaint is legally required under Nepal's E-Commerce Act.
AuditLog records sensitive admin actions (who changed a commission rate,
who resolved a complaint, when) — written via apps.support.services.audit().
"""
from django.conf import settings
from django.db import models


class GrievanceComplaint(models.Model):
    """Legal compliance — Nepal E-Commerce Act grievance handling."""

    class Category(models.TextChoices):
        PRODUCT_ISSUE = "product_issue", "Product issue"
        DELIVERY_ISSUE = "delivery_issue", "Delivery issue"
        PAYMENT_ISSUE = "payment_issue", "Payment issue"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In review"
        RESOLVED = "resolved", "Resolved"
        ESCALATED = "escalated", "Escalated"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="complaints")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "-created_at"])]


class Notification(models.Model):
    """User notification, delivered via SMS / push / in-app.

    SMS sending is offloaded to Celery (apps.support.tasks.send_sms_task) —
    user-facing requests never block on Sparrow SMS.
    """

    class Type(models.TextChoices):
        ORDER_UPDATE = "order_update", "Order update"
        PROMO = "promo", "Promotion"
        SYSTEM = "system", "System"

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        PUSH = "push", "Push"
        IN_APP = "in_app", "In-app"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=15, choices=Type.choices)
    title = models.CharField(max_length=120)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_via = models.CharField(max_length=10, choices=Channel.choices, default=Channel.SMS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]


class AuditLog(models.Model):
    """Immutable record of sensitive actions. ``user`` NULL = system action.
    Write-only by convention: no update/delete views, admin is read-only."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    model_affected = models.CharField(max_length=100)
    object_id = models.CharField(max_length=40)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["model_affected", "object_id"])]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user or 'system'}: {self.action}"


# =============================================================================
# Marketplace Improvement — Customer Support: persistent ticketing + live chat
# =============================================================================

class SupportTicket(models.Model):
    """
    Customer Support Ticketing System — persistent support entry point.
    
    Integrates with GrievanceComplaint for legal escalations.
    Supports live-chat style messaging via TicketMessage.
    """

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        WAITING_CUSTOMER = "waiting_customer", "Waiting for customer"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Channel(models.TextChoices):
        LIVE_CHAT = "live_chat", "Live Chat Widget"
        HELP_CENTER = "help_center", "Help Center Form"
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        WHATSAPP = "whatsapp", "WhatsApp"

    ticket_number = models.CharField(max_length=20, unique=True, db_index=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="support_tickets")
    guest_email = models.EmailField(blank=True, help_text="For guest live chat")
    guest_session = models.CharField(max_length=64, blank=True, db_index=True)
    subject = models.CharField(max_length=200)
    category = models.CharField(
        max_length=30,
        choices=GrievanceComplaint.Category.choices,
        default=GrievanceComplaint.Category.OTHER
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    channel = models.CharField(max_length=15, choices=Channel.choices, default=Channel.LIVE_CHAT)
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_tickets")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tickets")
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    satisfaction_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "-updated_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["priority", "status"]),
            models.Index(fields=["ticket_number"]),
        ]

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            # Generate MM-SUP-YYYY-XXXXXX
            import random, datetime
            today = datetime.date.today()
            self.ticket_number = f"MM-SUP-{today:%Y%m%d}-{random.randint(1000,9999)}"
        super().save(*args, **kwargs)

    @property
    def is_live_chat(self):
        return self.channel == self.Channel.LIVE_CHAT

    @property
    def response_time_minutes(self):
        if self.first_response_at and self.created_at:
            delta = self.first_response_at - self.created_at
            return int(delta.total_seconds() / 60)
        return None

    def __str__(self):
        return f"{self.ticket_number} — {self.subject[:40]}"


class TicketMessage(models.Model):
    """
    Live chat / ticketing message thread.
    Supports HTMX polling for near-real-time chat.
    """

    class SenderType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        AGENT = "agent", "Support Agent"
        SYSTEM = "system", "System"
        BOT = "bot", "Chat Bot"

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    sender_type = models.CharField(max_length=10, choices=SenderType.choices, default=SenderType.CUSTOMER)
    sender_name = models.CharField(max_length=100, blank=True, help_text="Guest display name")
    message = models.TextField()
    is_internal_note = models.BooleanField(default=False, help_text="Agent-only notes")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # attachments (future)
    attachment = models.FileField(upload_to="support_attachments/%Y/%m/", blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
            models.Index(fields=["sender_type"]),
        ]

    def __str__(self):
        return f"{self.ticket.ticket_number} {self.sender_type} @ {self.created_at:%H:%M}"


class LiveChatSession(models.Model):
    """
    Ephemeral live-chat session — powers persistent support FAB.
    Auto-converts to SupportTicket if unresolved after 5 min.
    """

    session_key = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    ticket = models.OneToOneField(SupportTicket, null=True, blank=True, on_delete=models.SET_NULL, related_name="chat_session")
    is_active = models.BooleanField(default=True)
    page_url = models.CharField(max_length=300, blank=True, help_text="Page where chat started — context")
    user_agent = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_reason = models.CharField(max_length=50, blank=True)

    class Meta:
        indexes = [models.Index(fields=["is_active", "-started_at"])]

    def __str__(self):
        return f"Chat {self.session_key[:8]} — {'active' if self.is_active else 'ended'}"

