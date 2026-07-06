"""
Views for orders app.
Handles cart, checkout, order management, and payments.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from .forms import ApplyCouponForm, CheckoutForm, CouponForm, OrderCancelForm, ReturnRequestForm
from .models import Cart, CartItem, Coupon, Order, OrderItem, Transaction, VendorPayout
from .services import (
    add_to_cart, calculate_delivery_fee, calculate_discount, calculate_vendor_payout,
    clear_cart, get_cart_items, get_cart_total, initiate_esewa_payment, 
    initiate_khalti_payment, merge_guest_cart, place_order, remove_from_cart,
    update_cart_item, update_order_status, validate_coupon
)
from apps.accounts.models import Address, User
from apps.catalog.models import Product, ProductVariant


# =============================================================================
# Cart Views
# =============================================================================

class CartView(LoginRequiredMixin, View):
    """Display shopping cart — with Transparent Pricing improvement."""
    
    template_name = 'orders/cart.html'
    
    def get(self, request):
        from .services import get_cart_pricing_breakdown
        # Performance: efficient query with select_related
        items = get_cart_items(user=request.user)
        subtotal = get_cart_total(user=request.user)

        # Transparent pricing — full payable before checkout
        # Try to use user's default address for shipping estimate
        default_address = None
        try:
            default_address = request.user.addresses.filter(is_default=True).first() or request.user.addresses.first()
        except Exception:
            pass

        try:
            pricing = get_cart_pricing_breakdown(
                user=request.user,
                delivery_address=default_address,
                coupon_code=request.GET.get('coupon')
            )
        except Exception:
            pricing = None
        
        context = {
            'cart_items': items,
            'subtotal': subtotal,
            'item_count': sum(item.quantity for item in items),
            'is_empty': len(items) == 0,
            'pricing': pricing,  # Transparent Pricing
            'default_address': default_address,
        }
        
        return render(request, self.template_name, context)


@require_POST
@login_required
def add_to_cart_ajax(request):
    """Add product to cart via HTMX/AJAX."""
    product_id = request.POST.get('product_id')
    quantity = int(request.POST.get('quantity', 1))
    variant_id = request.POST.get('variant_id')
    
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    variant = None
    if variant_id:
        variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
    
    item, error = add_to_cart(request.user, product, quantity, variant)
    
    if error:
        if request.headers.get('HX-Request'):
            return render(request, 'orders/partials/error_message.html', {'error': error})
        messages.error(request, error)
        return redirect('catalog:product_detail', slug=product.slug)
    
    cart_count = sum(i.quantity for i in get_cart_items(user=request.user))
    cart_total = get_cart_total(user=request.user)
    
    if request.headers.get('HX-Request'):
        context = {
            'item': item,
            'cart_count': cart_count,
            'cart_total': cart_total,
        }
        return render(request, 'orders/partials/cart_success.html', context)
    
    messages.success(request, f'Added {product.name} to cart!')
    return redirect('orders:cart')


@require_POST
@login_required
def update_cart_item_ajax(request):
    """Update cart item quantity via HTMX."""
    item_id = request.POST.get('item_id')
    quantity = int(request.POST.get('quantity', 1))
    
    item, error = update_cart_item(item_id, quantity)
    
    if error and not item:
        if request.headers.get('HX-Request'):
            return render(request, 'orders/partials/error_message.html', {'error': error})
        messages.error(request, error)
    
    items = get_cart_items(user=request.user)
    subtotal = get_cart_total(user=request.user)
    
    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/cart_items.html', {
            'cart_items': items,
            'subtotal': subtotal,
        })
    
    return redirect('orders:cart')


@require_POST
@login_required
def remove_cart_item_ajax(request, item_id):
    """Remove item from cart via HTMX."""
    success, error = remove_from_cart(item_id)
    
    if error:
        if request.headers.get('HX-Request'):
            return render(request, 'orders/partials/error_message.html', {'error': error})
        messages.error(request, error)
    
    items = get_cart_items(user=request.user)
    subtotal = get_cart_total(user=request.user)
    
    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/cart_items.html', {
            'cart_items': items,
            'subtotal': subtotal,
            'is_empty': len(items) == 0,
        })
    
    return redirect('orders:cart')


@require_POST
@login_required
def clear_cart_ajax(request):
    """Clear entire cart via HTMX."""
    clear_cart(user=request.user)
    
    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/cart_empty.html')
    
    messages.success(request, 'Cart cleared!')
    return redirect('orders:cart')


# =============================================================================
# Coupon Views
# =============================================================================

@require_POST
@login_required
def apply_coupon_ajax(request):
    """Apply coupon code via HTMX."""
    code = request.POST.get('code', '').strip().upper()
    subtotal = get_cart_total(user=request.user)
    
    coupon, error = validate_coupon(code, request.user, subtotal)
    
    if error:
        if request.headers.get('HX-Request'):
            return render(request, 'orders/partials/coupon_error.html', {'error': error})
        messages.error(request, error)
        return redirect('orders:cart')
    
    discount = calculate_discount(coupon, subtotal)
    
    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/coupon_success.html', {
            'coupon': coupon,
            'discount': discount,
            'new_total': subtotal - discount,
        })
    
    messages.success(request, f'Coupon applied! You save NPR {discount}')
    return redirect('orders:cart')


# =============================================================================
# Checkout Views
# =============================================================================

class CheckoutView(LoginRequiredMixin, View):
    """Checkout process."""
    
    template_name = 'orders/checkout.html'
    
    def get(self, request):
        items = get_cart_items(user=request.user)
        
        if not items:
            messages.warning(request, 'Your cart is empty!')
            return redirect('orders:cart')
        
        # Get addresses
        addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-id')
        
        form = CheckoutForm(user=request.user)
        
        context = {
            'cart_items': items,
            'subtotal': get_cart_total(user=request.user),
            'addresses': addresses,
            'form': form,
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request):
        items = get_cart_items(user=request.user)
        
        if not items:
            return redirect('orders:cart')
        
        form = CheckoutForm(data=request.POST, user=request.user)
        
        if form.is_valid():
            address = form.cleaned_data['address']
            payment_method = form.cleaned_data['payment_method']
            special_instructions = form.cleaned_data.get('special_instructions', '')
            coupon_code = request.POST.get('coupon_code', '')
            
            # Place order
            order, error = place_order(
                user=request.user,
                address=address,
                payment_method=payment_method,
                coupon_code=coupon_code if coupon_code else None,
                special_instructions=special_instructions
            )
            
            if error:
                messages.error(request, error)
                return redirect('orders:checkout')
            
            # Handle payment based on method
            if payment_method in ['esewa', 'khalti']:
                return redirect('orders:payment_redirect', order_id=order.id)
            else:  # COD
                messages.success(request, f'Order #{order.order_number} placed successfully!')
                return redirect('orders:order_confirmation', order_id=order.id)
        
        context = {
            'cart_items': items,
            'subtotal': get_cart_total(user=request.user),
            'addresses': Address.objects.filter(user=request.user).order_by('-is_default', '-id'),
            'form': form,
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# Payment Views
# =============================================================================

class PaymentRedirectView(LoginRequiredMixin, View):
    """Redirect to payment gateway."""
    
    template_name = 'orders/payment_redirect.html'
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        
        payment_url = None
        if order.payment_method == 'esewa':
            payment_url = initiate_esewa_payment(order)
        elif order.payment_method == 'khalti':
            payment_url = initiate_khalti_payment(order)
        
        context = {
            'order': order,
            'payment_url': payment_url,
        }
        
        return render(request, self.template_name, context)


class PaymentFailedView(LoginRequiredMixin, TemplateView):
    """Payment failure page."""
    
    template_name = 'orders/payment_failed.html'


class OrderConfirmationView(LoginRequiredMixin, View):
    """Order confirmation after successful placement."""
    
    template_name = 'orders/order_confirmation.html'
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        
        context = {
            'order': order,
            'items': order.items.select_related('product', 'variant', 'vendor'),
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# Order List/Detail Views
# =============================================================================

class OrderListView(LoginRequiredMixin, ListView):
    """List user's orders."""
    
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 10
    
    def get_queryset(self):
        return Order.objects.filter(
            customer=self.request.user
        ).select_related('delivery_address').prefetch_related('items').order_by('-placed_at')


class OrderDetailView(LoginRequiredMixin, View):
    """Display order details and granular timeline."""
    
    template_name = 'orders/order_detail.html'
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        user = request.user
        
        is_authorized = (
            order.customer == user or
            order.items.filter(vendor__user=user).exists() or
            (hasattr(order, 'delivery') and order.delivery.rider and order.delivery.rider.user == user) or
            user.is_staff or
            user.role == User.Role.ADMIN
        )
        if not is_authorized:
            raise PermissionDenied("You are not authorized to view this order timeline.")
        
        context = {
            'order': order,
            'items': order.items.select_related('product', 'variant', 'vendor'),
            'transactions': order.transactions.all().order_by('-created_at'),
            'delivery': getattr(order, 'delivery', None),
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# Order Cancellation
# =============================================================================

class OrderCancelView(LoginRequiredMixin, View):
    """Cancel an order — production bugfix: use service not model method."""
    
    template_name = 'orders/order_cancel.html'
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        # Prevent cancel if already delivered/cancelled
        if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
            messages.warning(request, 'This order can no longer be cancelled.')
            return redirect('orders:order_detail', order_id=order.id)
        form = OrderCancelForm()
        return render(request, self.template_name, {'order': order, 'form': form})
    
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        form = OrderCancelForm(data=request.POST)
        
        if form.is_valid():
            reason = form.cleaned_data['reason']
            # FIXED: use service cancel_order, not order.cancel_order (method doesn't exist)
            from .services import cancel_order as cancel_order_service
            success, error = cancel_order_service(order, request.user, reason)
            
            if success:
                messages.success(request, f'Order #{order.order_number} cancelled successfully.')
                return redirect('orders:order_list')
            else:
                messages.error(request, error or 'Cancellation failed.')
        
        return render(request, self.template_name, {'order': order, 'form': form})


# =============================================================================
# Return Request
# =============================================================================

class ReturnRequestView(LoginRequiredMixin, View):
    """Request a return for an order."""
    
    template_name = 'orders/return_request.html'
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        
        if order.status not in [Order.Status.DELIVERED, Order.Status.RETURNED]:
            messages.warning(request, 'Returns can only be requested for delivered orders.')
            return redirect('orders:order_detail', order_id=order.id)
        
        form = ReturnRequestForm()
        
        return render(request, self.template_name, {'order': order, 'form': form})
    
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        form = ReturnRequestForm(data=request.POST)
        
        if form.is_valid():
            # Create return request (would be a separate model in production)
            from apps.support.models import GrievanceComplaint
            
            complaint = GrievanceComplaint.objects.create(
                order=order,
                raised_by=request.user,
                category=GrievanceComplaint.Category.PRODUCT_ISSUE,
                description=f"Return Request - {form.cleaned_data['reason']}: {form.cleaned_data['description']}",
                status=GrievanceComplaint.Status.OPEN
            )
            
            # Update order status
            order.status = Order.Status.RETURNED
            order.save(update_fields=['status'])
            
            messages.success(request, 'Return request submitted! We will contact you soon.')
            return redirect('orders:order_detail', order_id=order.id)
        
        return render(request, self.template_name, {'order': order, 'form': form})


# =============================================================================
# Vendor Order Views
# =============================================================================

class VendorOrderListView(LoginRequiredMixin, View):
    """List vendor's orders."""
    
    template_name = 'orders/vendor_order_list.html'
    
    def get(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        orders = OrderItem.objects.filter(
            vendor=request.user.vendor_profile
        ).select_related('order', 'order__customer').order_by('-order__placed_at')
        
        # Group by order
        order_ids = orders.values_list('order_id', flat=True).distinct()
        orders_grouped = []
        
        for order_id in order_ids:
            order = Order.objects.get(id=order_id)
            vendor_items = orders.filter(order=order)
            orders_grouped.append({
                'order': order,
                'items': vendor_items,
                'total': sum(item.unit_price * item.quantity for item in vendor_items),
            })
        
        return render(request, self.template_name, {
            'orders': orders_grouped,
            'vendor': request.user.vendor_profile,
        })


class VendorOrderDetailView(LoginRequiredMixin, View):
    """Vendor view of order details."""
    
    template_name = 'orders/vendor_order_detail.html'
    
    def get(self, request, order_id):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        order = get_object_or_404(Order, id=order_id)
        vendor_items = order.items.filter(vendor=request.user.vendor_profile)
        
        if not vendor_items.exists():
            raise PermissionDenied("This order does not contain items from your store.")
        
        context = {
            'order': order,
            'vendor_items': vendor_items,
            'vendor': request.user.vendor_profile,
        }
        
        return render(request, self.template_name, context)


@require_POST
@login_required
def update_item_status_ajax(request):
    """Update order item status (vendor)."""
    item_id = request.POST.get('item_id')
    new_status = request.POST.get('status')
    
    if not hasattr(request.user, 'vendor_profile'):
        raise PermissionDenied("You are not a vendor.")
    
    try:
        item = OrderItem.objects.get(id=item_id, vendor=request.user.vendor_profile)
    except OrderItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'})
    
    if new_status in dict(OrderItem.ItemStatus.choices):
        item.item_status = new_status
        item.save(update_fields=['item_status'])
        
        # Update order status
        update_order_status(item.order)
        
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid status'})


class VendorEarningsView(LoginRequiredMixin, View):
    """Vendor earnings and payouts."""
    
    template_name = 'orders/vendor_earnings.html'
    
    def get(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        vendor = request.user.vendor_profile
        
        # Calculate totals
        delivered_items = OrderItem.objects.filter(
            vendor=vendor,
            item_status='delivered'
        )
        
        total_sales = delivered_items.aggregate(total=Sum('unit_price'))['total'] or 0
        total_commission = delivered_items.aggregate(total=Sum('commission_amount'))['total'] or 0
        net_earnings = total_sales - total_commission
        
        # Pending payouts
        pending_items = OrderItem.objects.filter(
            vendor=vendor,
            item_status__in=['pending', 'confirmed', 'preparing', 'ready']
        )
        pending_amount = pending_items.aggregate(total=Sum('unit_price'))['total'] or 0
        
        # Payout history
        payouts = VendorPayout.objects.filter(vendor=vendor).order_by('-period_end')
        
        context = {
            'vendor': vendor,
            'total_sales': total_sales,
            'total_commission': total_commission,
            'net_earnings': net_earnings,
            'pending_amount': pending_amount,
            'payouts': payouts,
        }
        
        return render(request, self.template_name, context)


# =============================================================================
# HTMX Partial Views
# =============================================================================

def cart_item_partial(request, item_id):
    """Return single cart item HTML."""
    try:
        item = CartItem.objects.get(id=item_id)
        return render(request, 'orders/partials/cart_item.html', {'item': item})
    except CartItem.DoesNotExist:
        return render(request, 'orders/partials/error_message.html', {'error': 'Item not found'})


def delivery_fee_partial(request, address_id):
    """Return delivery fee for an address."""
    address = get_object_or_404(Address, id=address_id, user=request.user)
    fee_info = calculate_delivery_fee(address)
    
    return render(request, 'orders/partials/delivery_fee.html', fee_info)


def order_status_partial(request, order_id):
    """Return order status timeline HTML."""
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    return render(request, 'orders/partials/order_status.html', {
        'order': order,
        'items': order.items.all(),
    })