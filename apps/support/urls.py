"""
URL patterns for support app.
"""
from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    # Help Center
    path("help-center/", views.HelpCenterView.as_view(), name="help_center"),
    
    # Complaints
    path("complaints/", views.ComplaintFormView.as_view(), name="complaint_form"),
    path("complaints/<int:order_id>/", views.ComplaintFormView.as_view(), name="complaint_form_with_order"),
    path("complaints/list/", views.ComplaintListView.as_view(), name="complaint_list"),
    path("complaints/<int:complaint_id>/", views.ComplaintDetailView.as_view(), name="complaint_detail"),
    
    # Admin Complaints
    path("admin/complaints/", views.AdminComplaintQueueView.as_view(), name="admin_complaint_queue"),
    path("admin/complaints/<int:complaint_id>/resolve/", views.resolve_complaint_ajax, name="resolve_complaint"),
    
    # Notifications
    path("notifications/", views.NotificationListView.as_view(), name="notification_list"),
    path("notifications/mark-read/", views.mark_notification_read_ajax, name="mark_notification_read"),
    path("notifications/mark-all-read/", views.mark_all_notifications_read_ajax, name="mark_all_read"),

    # --- Marketplace Improvement: Live Chat / Ticketing ---
    path("chat/messages/", views.chat_messages_ajax, name="chat_messages"),
    path("chat/send/", views.chat_send_ajax, name="chat_send"),

    # Customer Support Ticket details & replies
    path("tickets/<int:ticket_id>/", views.SupportTicketDetailView.as_view(), name="ticket_detail"),
    path("tickets/<int:ticket_id>/reply/", views.ticket_customer_reply, name="ticket_customer_reply"),

    # Support Team / Agent Chat Console
    path("agent/console/", views.AgentSupportConsoleView.as_view(), name="agent_console"),
    path("agent/console/<int:ticket_id>/", views.AgentSupportConsoleView.as_view(), name="agent_console_ticket"),
    path("agent/ticket/<int:ticket_id>/reply/", views.agent_ticket_reply, name="agent_ticket_reply"),
    path("agent/ticket/<int:ticket_id>/status/", views.agent_ticket_update_status, name="agent_ticket_status"),
]