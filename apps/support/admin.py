"""
Admin configuration for support app.
"""
from django.contrib import admin

from .models import AuditLog, GrievanceComplaint, Notification, SupportTicket, TicketMessage, LiveChatSession


@admin.register(GrievanceComplaint)
class GrievanceComplaintAdmin(admin.ModelAdmin):
    """Admin for GrievanceComplaint model."""
    
    list_display = ('id', 'order', 'raised_by', 'category', 'status', 'created_at', 'resolved_at')
    list_filter = ('status', 'category')
    search_fields = ('order__order_number', 'raised_by__email', 'description')
    raw_id_fields = ('order', 'raised_by')
    readonly_fields = ('created_at', 'resolved_at')
    
    fieldsets = (
        (None, {'fields': ('order', 'raised_by', 'category', 'status')}),
        ('Details', {'fields': ('description', 'resolution_notes')}),
        ('Timestamps', {'fields': ('created_at', 'resolved_at')}),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin for Notification model."""
    
    list_display = ('user', 'type', 'title', 'is_read', 'sent_via', 'created_at')
    list_filter = ('type', 'sent_via', 'is_read')
    search_fields = ('user__email', 'title', 'message')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog model (read-only)."""
    
    list_display = ('timestamp', 'user', 'action', 'model_affected', 'object_id', 'ip_address')
    list_filter = ('model_affected', 'action')
    search_fields = ('user__email', 'action', 'object_id')
    readonly_fields = ('user', 'action', 'model_affected', 'object_id', 'timestamp', 'ip_address')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# --- Marketplace Improvement: Support Ticketing Admin — allows admin to read & respond ---

class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 1
    fields = ('sender_type', 'sender', 'sender_name', 'message', 'is_internal_note', 'created_at')
    readonly_fields = ('created_at',)
    ordering = ('created_at',)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'subject', 'user', 'category', 'priority', 'status', 'channel', 'created_at')
    list_filter = ('status', 'priority', 'channel', 'category')
    search_fields = ('ticket_number', 'subject', 'user__email', 'guest_email')
    raw_id_fields = ('user', 'order', 'assigned_to')
    readonly_fields = ('ticket_number', 'created_at', 'updated_at', 'first_response_at')
    inlines = [TicketMessageInline]
    list_editable = ('status', 'priority')
    actions = ['mark_in_progress', 'mark_resolved']

    def mark_in_progress(self, request, queryset):
        queryset.update(status=SupportTicket.Status.IN_PROGRESS)
    mark_in_progress.short_description = "Mark in progress"

    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        queryset.update(status=SupportTicket.Status.RESOLVED, resolved_at=timezone.now())
    mark_resolved.short_description = "Mark resolved — admin responded"


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'sender_type', 'sender', 'short_message', 'created_at', 'is_internal_note')
    list_filter = ('sender_type', 'is_internal_note')
    search_fields = ('ticket__ticket_number', 'message')
    raw_id_fields = ('ticket', 'sender')

    def short_message(self, obj):
        return obj.message[:60]
    short_message.short_description = 'Message'


@admin.register(LiveChatSession)
class LiveChatSessionAdmin(admin.ModelAdmin):
    list_display = ('session_key', 'user', 'ticket', 'is_active', 'started_at')
    list_filter = ('is_active',)
    search_fields = ('session_key', 'user__email')