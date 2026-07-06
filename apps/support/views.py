"""
Views for support app.
Handles help center, complaints, notifications, and admin complaint queue.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from .forms import ComplaintResolutionForm, GrievanceComplaintForm
from .models import AuditLog, GrievanceComplaint, Notification, SupportTicket, TicketMessage, LiveChatSession
from .services import (
    create_complaint, get_faq_categories, get_model_audit_trail, 
    get_pending_complaints, get_unread_notification_count, get_user_complaints,
    get_user_notifications, mark_all_notifications_read, mark_notification_read,
    update_complaint_status
)
from apps.accounts.models import User
from apps.orders.models import Order


# =============================================================================
# Help Center
# =============================================================================

class HelpCenterView(TemplateView):
    """Help center with FAQs."""
    
    template_name = 'support/help_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['faq_categories'] = get_faq_categories()
        return context


# =============================================================================
# Complaint Views
# =============================================================================

class ComplaintFormView(LoginRequiredMixin, View):
    """Create a new complaint/grievance."""
    
    template_name = 'support/complaint_form.html'
    
    def get(self, request, order_id=None):
        order = None
        if order_id:
            order = get_object_or_404(Order, id=order_id, customer=request.user)
        
        form = GrievanceComplaintForm()
        return render(request, self.template_name, {'form': form, 'order': order})
    
    def post(self, request, order_id=None):
        order = None
        if order_id:
            order = get_object_or_404(Order, id=order_id, customer=request.user)
        else:
            # Get most recent order
            order = Order.objects.filter(customer=request.user).first()
        
        if not order:
            messages.error(request, 'No order found to file complaint for.')
            return redirect('support:help_center')
        
        form = GrievanceComplaintForm(data=request.POST)
        if form.is_valid():
            complaint = create_complaint(
                order=order,
                user=request.user,
                category=form.cleaned_data['category'],
                description=form.cleaned_data['description']
            )
            
            messages.success(request, f'Complaint #{complaint.id} filed successfully! We will review it shortly.')
            
            if request.headers.get('HX-Request'):
                return render(request, 'support/partials/complaint_success.html', {'complaint': complaint})
            
            return redirect('support:complaint_detail', complaint_id=complaint.id)
        
        return render(request, self.template_name, {'form': form, 'order': order})


class ComplaintListView(LoginRequiredMixin, ListView):
    """List user's complaints and support tickets."""
    
    model = GrievanceComplaint
    template_name = 'support/complaint_list.html'
    context_object_name = 'complaints'
    paginate_by = 10
    
    def get_queryset(self):
        return get_user_complaints(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['support_tickets'] = SupportTicket.objects.filter(user=self.request.user).order_by('-updated_at')
        return context


class ComplaintDetailView(LoginRequiredMixin, View):
    """View complaint details."""
    
    template_name = 'support/complaint_detail.html'
    
    def get(self, request, complaint_id):
        complaint = get_object_or_404(GrievanceComplaint, id=complaint_id, raised_by=request.user)
        
        context = {
            'complaint': complaint,
            'audit_trail': get_model_audit_trail('GrievanceComplaint', complaint.id),
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# Admin Complaint Views
# =============================================================================

class AdminComplaintQueueView(LoginRequiredMixin, TemplateView):
    """Admin view of all complaints."""
    
    template_name = 'support/admin_complaint_queue.html'
    
    def get(self, request):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        status_filter = request.GET.get('status', 'all')
        
        complaints = GrievanceComplaint.objects.select_related(
            'order', 'raised_by'
        ).order_by('-created_at')
        
        if status_filter != 'all':
            complaints = complaints.filter(status=status_filter)
        
        # Pagination
        page = request.GET.get('page', 1)
        paginator = Paginator(complaints, 20)
        try:
            complaints_page = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            complaints_page = paginator.page(1)
        
        context = {
            'complaints': complaints_page,
            'status_filter': status_filter,
            'status_counts': {
                'all': GrievanceComplaint.objects.count(),
                'open': GrievanceComplaint.objects.filter(status='open').count(),
                'in_review': GrievanceComplaint.objects.filter(status='in_review').count(),
                'resolved': GrievanceComplaint.objects.filter(status='resolved').count(),
                'escalated': GrievanceComplaint.objects.filter(status='escalated').count(),
            }
        }
        
        return render(request, self.template_name, context)


@login_required
def resolve_complaint_ajax(request, complaint_id):
    """Resolve a complaint (admin)."""
    if not request.user.is_staff and request.user.role != User.Role.ADMIN:
        raise PermissionDenied("Admin access required.")
    
    complaint = get_object_or_404(GrievanceComplaint, id=complaint_id)
    
    if request.method == 'POST':
        form = ComplaintResolutionForm(data=request.POST, instance=complaint)
        if form.is_valid():
            update_complaint_status(
                complaint=complaint,
                new_status=form.cleaned_data['status'],
                notes=form.cleaned_data['resolution_notes'],
                updated_by=request.user
            )
            
            messages.success(request, f'Complaint #{complaint.id} updated successfully.')
            
            if request.headers.get('HX-Request'):
                return render(request, 'support/partials/complaint_resolved.html', {'complaint': complaint})
            
            return redirect('support:admin_complaint_queue')
        
        return render(request, 'support/partials/complaint_resolution_form.html', {
            'complaint': complaint,
            'form': form
        })
    
    form = ComplaintResolutionForm(instance=complaint)
    return render(request, 'support/partials/complaint_resolution_form.html', {
        'complaint': complaint,
        'form': form
    })


# =============================================================================
# Notification Views
# =============================================================================

class NotificationListView(LoginRequiredMixin, ListView):
    """List user notifications."""
    
    model = Notification
    template_name = 'support/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return get_user_notifications(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_count'] = get_unread_notification_count(self.request.user)
        return context


@require_POST
@login_required
def mark_notification_read_ajax(request):
    """Mark a notification as read via HTMX."""
    notification_id = request.POST.get('notification_id')
    
    if mark_notification_read(int(notification_id), request.user):
        if request.headers.get('HX-Request'):
            count = get_unread_notification_count(request.user)
            return render(request, 'support/partials/notification_badge.html', {'unread_count': count})
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Notification not found'})


@require_POST
@login_required
def mark_all_notifications_read_ajax(request):
    """Mark all notifications as read via HTMX."""
    count = mark_all_notifications_read(request.user)
    
    if request.headers.get('HX-Request'):
        notifications = get_user_notifications(request.user)[:10]
        return render(request, 'support/partials/notification_list.html', {
            'notifications': notifications,
            'unread_count': 0
        })
    
    return JsonResponse({'success': True, 'count': count})


# =============================================================================
# Marketplace Improvement — Customer Support: Live Chat + Ticketing
# =============================================================================

from .models import SupportTicket, TicketMessage, LiveChatSession
from django.views.decorators.csrf import csrf_exempt

def get_or_create_chat_session(request):
    """Get or create live chat session — persistent support entry point."""
    session_key = request.session.session_key
    if not session_key:
        request.session.save()
        session_key = request.session.session_key
    chat_session, _ = LiveChatSession.objects.get_or_create(
        session_key=session_key,
        defaults={
            'user': request.user if request.user.is_authenticated else None,
            'page_url': request.META.get('HTTP_REFERER', '')[:300],
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
        }
    )
    return chat_session

@require_http_methods(["GET"])
@login_required
def chat_messages_ajax(request):
    """HTMX polling endpoint — returns recent chat messages — LOGIN REQUIRED (Marketplace Improvement #3)."""
    chat_session = get_or_create_chat_session(request)
    chat_session = get_or_create_chat_session(request)
    # Find or create ticket
    ticket = chat_session.ticket
    if not ticket:
        # auto-create lightweight ticket on first poll
        ticket = SupportTicket.objects.create(
            user=request.user if request.user.is_authenticated else None,
            guest_session=chat_session.session_key,
            guest_email='',
            subject='Live chat started from ' + (chat_session.page_url or 'homepage')[:80],
            channel=SupportTicket.Channel.LIVE_CHAT,
            category='other',
            priority=SupportTicket.Priority.MEDIUM,
        )
        chat_session.ticket = ticket
        chat_session.save(update_fields=['ticket'])
        # seed bot welcome
        TicketMessage.objects.create(
            ticket=ticket,
            sender_type=TicketMessage.SenderType.BOT,
            sender_name='Makwanpur Mart Bot',
            message='Namaste! 🙏 I am Hetauda support bot. A human agent typically replies within 2 minutes 9am–7pm NPT. How can I help?'
        )

    messages_qs = ticket.messages.filter(is_internal_note=False).order_by('-created_at')[:20]
    messages_qs = reversed(messages_qs)
    # Simple HTML render inline (avoid needing template file)
    html_parts = []
    for m in messages_qs:
        is_customer = m.sender_type == TicketMessage.SenderType.CUSTOMER
        align = 'ml-auto text-right bg-brand-marigold/20' if is_customer else 'mr-auto bg-white'
        sender_label = 'You' if is_customer else (m.sender_name or 'Support Agent' if m.sender_type=='agent' else 'Support Bot')
        html_parts.append(f'''
        <div class="border rounded-stall p-2 max-w-[85%] {align}">
            <div class="font-bold text-[11px] text-brand-indigo">{sender_label}</div>
            <div class="text-neutral-800 mt-0.5">{m.message}</div>
            <div class="text-[10px] text-neutral-500 mt-1">{m.created_at.strftime("%H:%M")}</div>
        </div>
        ''')
    if not html_parts:
        return JsonResponse({'html': ''})
    from django.http import HttpResponse
    return HttpResponse(''.join(html_parts))

@require_POST
@login_required
def chat_send_ajax(request):
    """Receive live chat message — creates TicketMessage, auto-reply bot — LOGIN REQUIRED."""
    from django.utils.html import escape
    message_text = request.POST.get('message', '').strip()
    if not message_text:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest('Empty')

    chat_session = get_or_create_chat_session(request)
    ticket = chat_session.ticket
    if not ticket:
        # create quickly
        ticket = SupportTicket.objects.create(
            user=request.user if request.user.is_authenticated else None,
            guest_session=chat_session.session_key,
            subject=message_text[:120],
            channel=SupportTicket.Channel.LIVE_CHAT,
        )
        chat_session.ticket = ticket
        chat_session.save(update_fields=['ticket'])

    # save customer message
    msg = TicketMessage.objects.create(
        ticket=ticket,
        sender=request.user if request.user.is_authenticated else None,
        sender_type=TicketMessage.SenderType.CUSTOMER,
        sender_name=request.user.get_full_name() if request.user.is_authenticated else 'Guest',
        message=message_text[:2000]
    )
    # update ticket timestamp
    ticket.save(update_fields=['updated_at'])

    # auto bot reply (simple keyword)
    bot_reply = None
    low = message_text.lower()
    if any(k in low for k in ['order', 'track', 'delivery', 'where']):
        bot_reply = 'Track your order here: <a href="/orders/" class="text-brand-indigo underline">My Orders →</a> Hyperlocal SLA is 2-4hrs in Hetauda wards 1-19.'
    elif any(k in low for k in ['return', 'refund', 'replace']):
        bot_reply = 'Our return policy is shown on EVERY product page. 3-day doorstep replacement. Start here: <a href="/return-policy/" class="text-brand-indigo underline">Return Policy</a>'
    elif any(k in low for k in ['payment', 'esewa', 'khalti', 'cod']):
        bot_reply = 'We accept eSewa, Khalti, and Cash on Delivery — all equally prominent at 2-step checkout. No hidden fees.'
    elif any(k in low for k in ['seller', 'vendor', 'verified']):
        bot_reply = 'Look for the ✓ Verified Vendor badge — dynamically checked from our database. Trust score & seller ratings shown on every product page.'
    else:
        bot_reply = 'Thanks! A Hetauda support agent will reply shortly (avg 2 min, 9am–7pm). Meanwhile: <a href="/support/help-center/" class="underline text-brand-indigo">Help Center</a>'

    if bot_reply:
        TicketMessage.objects.create(
            ticket=ticket,
            sender_type=TicketMessage.SenderType.BOT,
            sender_name='Support Bot',
            message=bot_reply
        )

    # return rendered customer bubble + bot bubble for HTMX
    from django.http import HttpResponse
    from django.utils.safestring import mark_safe
    customer_html = f'''
    <div class="border rounded-stall p-2 max-w-[85%] ml-auto text-right bg-brand-marigold/20">
        <div class="font-bold text-[11px] text-brand-indigo">You</div>
        <div class="text-neutral-800 mt-0.5">{escape(message_text)}</div>
        <div class="text-[10px] text-neutral-500 mt-1">now</div>
    </div>
    <div class="border rounded-stall p-2 max-w-[85%] mr-auto bg-white">
        <div class="font-bold text-[11px] text-brand-indigo">Support Bot</div>
        <div class="text-neutral-800 mt-0.5">{bot_reply}</div>
        <div class="text-[10px] text-neutral-500 mt-1">now • auto</div>
    </div>
    '''
    return HttpResponse(mark_safe(customer_html))


# =============================================================================
# Support Team Agent Console & Persistent Ticket Views
# =============================================================================

class AgentSupportConsoleView(LoginRequiredMixin, View):
    """Support Team Agent Console — easy access interface for support staff to chat & manage tickets."""
    template_name = 'support/agent_console.html'

    def get(self, request, ticket_id=None):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Support agent access required.")

        status_filter = request.GET.get('status', 'open')
        tickets_qs = SupportTicket.objects.select_related('user', 'order', 'assigned_to').order_by('-updated_at')

        if status_filter != 'all':
            if status_filter == 'open':
                tickets_qs = tickets_qs.filter(status__in=[SupportTicket.Status.OPEN, SupportTicket.Status.WAITING_CUSTOMER, SupportTicket.Status.IN_PROGRESS])
            else:
                tickets_qs = tickets_qs.filter(status=status_filter)

        active_ticket = None
        if ticket_id:
            active_ticket = get_object_or_404(SupportTicket, id=ticket_id)
        elif tickets_qs.exists():
            active_ticket = tickets_qs.first()

        messages_list = []
        if active_ticket:
            messages_list = active_ticket.messages.select_related('sender').order_by('created_at')

        context = {
            'tickets': tickets_qs[:50],
            'active_ticket': active_ticket,
            'messages_list': messages_list,
            'status_filter': status_filter,
            'stats': {
                'open_count': SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count(),
                'in_progress_count': SupportTicket.objects.filter(status=SupportTicket.Status.IN_PROGRESS).count(),
                'waiting_count': SupportTicket.objects.filter(status=SupportTicket.Status.WAITING_CUSTOMER).count(),
                'grievance_count': GrievanceComplaint.objects.filter(status='open').count(),
            }
        }
        return render(request, self.template_name, context)


@require_POST
@login_required
def agent_ticket_reply(request, ticket_id):
    """Support Agent replies to a ticket or live chat thread."""
    if not request.user.is_staff and request.user.role != User.Role.ADMIN:
        raise PermissionDenied("Support agent access required.")

    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    msg_text = request.POST.get('message', '').strip()
    is_internal = request.POST.get('is_internal_note') == '1'
    new_status = request.POST.get('status', SupportTicket.Status.WAITING_CUSTOMER)

    if msg_text:
        TicketMessage.objects.create(
            ticket=ticket,
            sender=request.user,
            sender_type=TicketMessage.SenderType.AGENT,
            sender_name=request.user.get_full_name() or request.user.username or 'Support Agent',
            message=msg_text,
            is_internal_note=is_internal
        )
        if not is_internal:
            ticket.status = new_status
            if not ticket.first_response_at:
                ticket.first_response_at = timezone.now()
        ticket.assigned_to = request.user
        ticket.save(update_fields=['status', 'first_response_at', 'assigned_to', 'updated_at'])
        messages.success(request, f'Reply sent to ticket #{ticket.ticket_number}.')

    return redirect('support:agent_console_ticket', ticket_id=ticket.id)


@require_POST
@login_required
def agent_ticket_update_status(request, ticket_id):
    """Support Agent updates status or assigns ticket."""
    if not request.user.is_staff and request.user.role != User.Role.ADMIN:
        raise PermissionDenied("Support agent access required.")

    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    status = request.POST.get('status')
    assign_me = request.POST.get('assign_me') == '1'

    if status and status in dict(SupportTicket.Status.choices):
        ticket.status = status
        if status == SupportTicket.Status.RESOLVED:
            ticket.resolved_at = timezone.now()
        ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
        messages.success(request, f'Ticket #{ticket.ticket_number} status updated to {ticket.get_status_display()}.')

    if assign_me:
        ticket.assigned_to = request.user
        ticket.save(update_fields=['assigned_to', 'updated_at'])
        messages.success(request, f'Assigned ticket #{ticket.ticket_number} to yourself.')

    return redirect('support:agent_console_ticket', ticket_id=ticket.id)


class SupportTicketDetailView(LoginRequiredMixin, View):
    """Customer view of persistent support ticket thread."""
    template_name = 'support/ticket_detail.html'

    def get(self, request, ticket_id):
        ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)
        messages_list = ticket.messages.filter(is_internal_note=False).order_by('created_at')
        return render(request, self.template_name, {'ticket': ticket, 'messages_list': messages_list})


@require_POST
@login_required
def ticket_customer_reply(request, ticket_id):
    """Customer replies to their support ticket thread."""
    ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)
    msg_text = request.POST.get('message', '').strip()
    if msg_text:
        TicketMessage.objects.create(
            ticket=ticket,
            sender=request.user,
            sender_type=TicketMessage.SenderType.CUSTOMER,
            sender_name=request.user.get_full_name() or request.user.username,
            message=msg_text
        )
        ticket.status = SupportTicket.Status.OPEN
        ticket.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Message sent!')
    return redirect('support:ticket_detail', ticket_id=ticket.id)