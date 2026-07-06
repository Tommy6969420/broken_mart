"""
Views for delivery app.
Handles delivery management, rider assignments, and tracking.
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

from .forms import DeliveryAssignmentForm, DeliveryStatusUpdateForm, DeliveryZoneForm
from .models import Delivery, DeliveryZone
from .services import (
    accept_delivery, complete_delivery, get_delivery_stats, get_rider_active_deliveries,
    get_rider_delivery_history, unassign_delivery, update_delivery_status
)
from apps.accounts.models import RiderProfile, User


# =============================================================================
# Delivery Detail View
# =============================================================================

class DeliveryDetailView(LoginRequiredMixin, View):
    """Display delivery details (for customer tracking)."""
    
    template_name = 'delivery/delivery_detail.html'
    
    def get(self, request, delivery_id):
        delivery = get_object_or_404(Delivery, id=delivery_id)
        
        # Check authorization
        user = request.user
        is_authorized = (
            delivery.order.customer == user or
            delivery.rider == getattr(user, 'rider_profile', None) or
            user.is_staff or
            user.role == User.Role.ADMIN
        )
        
        if not is_authorized:
            raise PermissionDenied("You are not authorized to view this delivery.")
        
        context = {
            'delivery': delivery,
            'order': delivery.order,
            'rider': delivery.rider,
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# Rider Delivery Views
# =============================================================================

class RiderDeliveryListView(LoginRequiredMixin, View):
    """List rider's deliveries."""
    
    template_name = 'delivery/rider_delivery_list.html'
    
    def get(self, request):
        if not hasattr(request.user, 'rider_profile'):
            raise PermissionDenied("You are not a rider.")
        
        rider = request.user.rider_profile
        
        # Get active and available deliveries
        active_deliveries = get_rider_active_deliveries(rider)
        history = get_rider_delivery_history(rider, limit=20)
        
        context = {
            'rider': rider,
            'active_deliveries': active_deliveries,
            'history': history,
            'is_available': rider.is_available,
            'current_zone': rider.current_zone,
        }
        
        return render(request, self.template_name, context)


@require_POST
@login_required
def rider_accept_delivery(request, delivery_id):
    """Rider accepts a delivery assignment."""
    if not hasattr(request.user, 'rider_profile'):
        raise PermissionDenied("You are not a rider.")
    
    success, error = accept_delivery(request.user.rider_profile, delivery_id)
    
    if success:
        messages.success(request, 'Delivery accepted!')
    else:
        messages.error(request, error or 'Failed to accept delivery.')
    
    if request.headers.get('HX-Request'):
        return render(request, 'delivery/partials/delivery_accepted.html', {'delivery_id': delivery_id})
    
    return redirect('delivery:rider_delivery_list')


@require_POST
@login_required
def rider_update_status(request, delivery_id):
    """Rider updates delivery status."""
    if not hasattr(request.user, 'rider_profile'):
        raise PermissionDenied("You are not a rider.")
    
    delivery = get_object_or_404(Delivery, id=delivery_id, rider=request.user.rider_profile)
    new_status = request.POST.get('status')
    failure_reason = request.POST.get('failure_reason', '')
    
    if new_status == 'delivered':
        success, error = complete_delivery(delivery_id)
    else:
        success, error = update_delivery_status(delivery_id, new_status, failure_reason)
    
    if success:
        messages.success(request, f'Delivery status updated to {new_status}!')
    else:
        messages.error(request, error or 'Failed to update status.')
    
    if request.headers.get('HX-Request'):
        delivery.refresh_from_db()
        return render(request, 'delivery/partials/delivery_status_updated.html', {
            'delivery': delivery
        })
    
    return redirect('delivery:rider_delivery_list')


@require_POST
@login_required
def toggle_availability(request):
    """Toggle rider availability."""
    if not hasattr(request.user, 'rider_profile'):
        return JsonResponse({'success': False, 'error': 'Not a rider'})
    
    rider = request.user.rider_profile
    rider.is_available = not rider.is_available
    rider.save(update_fields=['is_available'])
    
    return JsonResponse({
        'success': True,
        'is_available': rider.is_available
    })


# =============================================================================
# Admin Delivery Management
# =============================================================================

class AdminDeliveryListView(LoginRequiredMixin, TemplateView):
    """Admin view of all deliveries."""
    
    template_name = 'delivery/admin_delivery_list.html'
    
    def get(self, request):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        status_filter = request.GET.get('status', 'all')
        
        deliveries = Delivery.objects.select_related(
            'order', 'order__customer', 'rider', 'rider__user'
        ).order_by('-assigned_at')
        
        if status_filter != 'all':
            deliveries = deliveries.filter(status=status_filter)
        
        # Pagination
        page = request.GET.get('page', 1)
        paginator = Paginator(deliveries, 25)
        try:
            deliveries_page = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            deliveries_page = paginator.page(1)
        
        context = {
            'deliveries': deliveries_page,
            'status_filter': status_filter,
            'stats': get_delivery_stats(),
            'zones': DeliveryZone.objects.filter(is_active=True),
        }
        
        return render(request, self.template_name, context)


@require_POST
@login_required
def admin_assign_delivery(request, delivery_id):
    """Admin assigns a delivery to a rider."""
    if not request.user.is_staff and request.user.role != User.Role.ADMIN:
        raise PermissionDenied("Admin access required.")
    
    delivery = get_object_or_404(Delivery, id=delivery_id, status='unassigned')
    form = DeliveryAssignmentForm(data=request.POST, instance=delivery)
    
    if form.is_valid():
        rider = form.cleaned_data['rider']
        if rider:
            success, error = accept_delivery(rider, delivery_id)
            if success:
                messages.success(request, f'Delivery assigned to {rider.user.username}!')
            else:
                messages.error(request, error)
        else:
            messages.warning(request, 'Please select a rider.')
    
    if request.headers.get('HX-Request'):
        delivery.refresh_from_db()
        return render(request, 'delivery/partials/delivery_assigned.html', {
            'delivery': delivery
        })
    
    return redirect('delivery:admin_delivery_list')


# =============================================================================
# Zone Management (Admin)
# =============================================================================

class DeliveryZoneListView(LoginRequiredMixin, TemplateView):
    """Admin view of delivery zones."""
    
    template_name = 'delivery/zone_list.html'
    
    def get(self, request):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        zones = DeliveryZone.objects.all().order_by('name')
        return render(request, self.template_name, {'zones': zones})


class DeliveryZoneCreateView(LoginRequiredMixin, View):
    """Create a delivery zone."""
    
    template_name = 'delivery/zone_form.html'
    
    def get(self, request):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        form = DeliveryZoneForm()
        return render(request, self.template_name, {'form': form, 'zone': None})
    
    def post(self, request):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        form = DeliveryZoneForm(data=request.POST)
        if form.is_valid():
            zone = form.save()
            messages.success(request, f'Zone "{zone.name}" created!')
            return redirect('delivery:zone_list')
        
        return render(request, self.template_name, {'form': form, 'zone': None})


class DeliveryZoneEditView(LoginRequiredMixin, View):
    """Edit a delivery zone."""
    
    template_name = 'delivery/zone_form.html'
    
    def get(self, request, zone_id):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        zone = get_object_or_404(DeliveryZone, id=zone_id)
        form = DeliveryZoneForm(instance=zone)
        return render(request, self.template_name, {'form': form, 'zone': zone})
    
    def post(self, request, zone_id):
        if not request.user.is_staff and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Admin access required.")
        
        zone = get_object_or_404(DeliveryZone, id=zone_id)
        form = DeliveryZoneForm(data=request.POST, instance=zone)
        
        if form.is_valid():
            form.save()
            messages.success(request, f'Zone "{zone.name}" updated!')
            return redirect('delivery:zone_list')
        
        return render(request, self.template_name, {'form': form, 'zone': zone})


# =============================================================================
# HTMX Partial Views
# =============================================================================

def delivery_tracking_partial(request, delivery_id):
    """Return delivery tracking HTML for customer."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    
    return render(request, 'delivery/partials/tracking_timeline.html', {
        'delivery': delivery,
        'order': delivery.order,
        'rider': delivery.rider,
    })


def rider_delivery_card_partial(request, delivery_id):
    """Return rider delivery card HTML."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    
    return render(request, 'delivery/partials/rider_delivery_card.html', {
        'delivery': delivery,
        'order': delivery.order,
    })