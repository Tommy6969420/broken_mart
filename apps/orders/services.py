"""
Services for orders app.
Business logic for cart, checkout, orders, payments, and delivery fee calculation.
"""
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import Cart, CartItem, Coupon, Order, OrderItem, Transaction, VendorPayout


# =============================================================================
# Cart Services
# =============================================================================

def get_or_create_cart(user=None, session_key=None):
    """
    Get or create a cart for the user or session.
    """
    if user:
        cart, created = Cart.objects.get_or_create(user=user)
    elif session_key:
        cart, created = Cart.objects.get_or_create(session_key=session_key)
    else:
        return None
    
    return cart


def get_cart_items(user=None, session_key=None):
    """Get all items in the cart."""
    cart = get_or_create_cart(user=user, session_key=session_key)
    if not cart:
        return []
    
    return CartItem.objects.filter(cart=cart).select_related(
        'product', 'product__vendor', 'product__category'
    ).prefetch_related('product__images', 'variant')


def get_cart_total(user=None, session_key=None):
    """Calculate cart subtotal."""
    items = get_cart_items(user=user, session_key=session_key)
    total = Decimal('0.00')
    
    for item in items:
        price = item.variant.effective_price if item.variant else item.product.effective_price
        total += price * item.quantity
    
    return total


def add_to_cart(user, product, quantity=1, variant=None):
    """
    Add product to cart.
    If product already in cart, update quantity.
    """
    cart = get_or_create_cart(user=user)
    
    # Check stock
    from apps.catalog.services import check_product_available
    if not check_product_available(product, quantity, variant):
        return None, "Not enough stock available"
    
    # Get or create cart item
    try:
        item = CartItem.objects.get(
            cart=cart,
            product=product,
            variant=variant
        )
        item.quantity += quantity
        item.save(update_fields=['quantity'])
    except CartItem.DoesNotExist:
        item = CartItem.objects.create(
            cart=cart,
            product=product,
            variant=variant,
            quantity=quantity
        )
    
    return item, None


def update_cart_item(item_id, quantity):
    """Update cart item quantity."""
    try:
        item = CartItem.objects.get(id=item_id)
        
        if quantity <= 0:
            item.delete()
            return None, None
        else:
            # Check stock
            from apps.catalog.services import check_product_available
            if not check_product_available(item.product, quantity, item.variant):
                return item, "Not enough stock available"
            
            item.quantity = quantity
            item.save(update_fields=['quantity'])
            return item, None
    except CartItem.DoesNotExist:
        return None, "Item not found"


def remove_from_cart(item_id):
    """Remove item from cart."""
    try:
        item = CartItem.objects.get(id=item_id)
        item.delete()
        return True, None
    except CartItem.DoesNotExist:
        return False, "Item not found"


def clear_cart(user=None, session_key=None):
    """Clear all items from cart."""
    cart = get_or_create_cart(user=user, session_key=session_key)
    if cart:
        cart.items.all().delete()
    return True


def merge_guest_cart(user, session_key):
    """
    Merge guest cart into user cart on login.
    """
    try:
        guest_cart = Cart.objects.get(session_key=session_key)
    except Cart.DoesNotExist:
        return
    
    user_cart = get_or_create_cart(user=user)
    
    if not guest_cart.items.exists():
        return
    
    for guest_item in guest_cart.items.all():
        try:
            # Check if product already in user cart
            user_item = CartItem.objects.get(
                cart=user_cart,
                product=guest_item.product,
                variant=guest_item.variant
            )
            # Merge quantities
            user_item.quantity += guest_item.quantity
            user_item.save(update_fields=['quantity'])
        except CartItem.DoesNotExist:
            # Move item to user cart
            guest_item.cart = user_cart
            guest_item.save(update_fields=['cart'])
    
    # Delete guest cart
    guest_cart.delete()


# =============================================================================
# Delivery Fee Calculation
# =============================================================================

def calculate_delivery_fee(address):
    """
    Calculate delivery fee based on address zone.
    """
    from apps.delivery.models import DeliveryZone
    
    try:
        zone = DeliveryZone.objects.filter(
            is_active=True,
            ward_numbers__contains=address.ward_number
        ).first()
        
        if zone:
            return {
                'deliverable': True,
                'fee': zone.base_delivery_fee,
                'estimated_minutes': zone.estimated_delivery_time_minutes,
                'zone_name': zone.name,
            }
    except Exception:
        pass
    
    return {
        'deliverable': False,
        'fee': Decimal('0.00'),
        'estimated_minutes': 0,
        'message': 'Delivery not available to this address'
    }


# =============================================================================
# Coupon Services
# =============================================================================

def validate_coupon(code, user, order_total):
    """
    Validate a coupon code — production bugfix.
    Returns (coupon, error_message)

    Fixes: Coupon model uses `value`, `usage_limit`, `times_used`
    NOT `discount_value`, `max_uses`, `minimum_order_amount`
    """
    from django.db.models import F
    code = code.strip().upper()
    
    try:
        # select_for_update prevents race on times_used
        coupon = Coupon.objects.select_for_update().get(code__iexact=code, is_active=True)
    except Coupon.DoesNotExist:
        return None, "Invalid coupon code"
    
    now = timezone.now()
    
    # Check validity period
    if coupon.valid_from and coupon.valid_from > now:
        return None, "This coupon is not yet active"
    
    if coupon.valid_until and coupon.valid_until < now:
        return None, "This coupon has expired"
    
    # Check usage limit — FIXED field names
    # usage_limit vs times_used (not max_uses / orders.count())
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        return None, "This coupon has reached its usage limit"
    
    # Check per-user limit — one use per user
    if coupon.orders.filter(customer=user).exists():
        return None, "You have already used this coupon"
    
    # Vendor-specific coupon check
    # (If coupon.vendor is set, ensure cart contains that vendor's products — simplified: allow, checked at order time)
    
    # Minimum order amount — Coupon model doesn't have minimum_order_amount field
    # Skipping — could add field later. For now: no minimum.

    return coupon, None


def calculate_discount(coupon, order_total):
    """Calculate discount amount based on coupon type — FIXED field names."""
    from decimal import Decimal
    order_total = Decimal(str(order_total))
    # FIXED: coupon.value not coupon.discount_value
    if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
        discount = order_total * (coupon.value / Decimal('100'))
        # Cap at order total
        return min(discount, order_total).quantize(Decimal('0.01'))
    else:  # flat
        return min(coupon.value, order_total).quantize(Decimal('0.01'))


# =============================================================================
# Order Placement
# =============================================================================

@transaction.atomic
def place_order(user, address, payment_method, coupon_code=None, special_instructions=''):
    """
    Place an order from the cart.
    Creates order, order items, and initiates payment.
    """
    cart_items = list(get_cart_items(user=user))
    
    if not cart_items:
        return None, "Your cart is empty"
    
    # Calculate totals
    subtotal = get_cart_total(user=user)
    
    # Delivery fee
    delivery_info = calculate_delivery_fee(address)
    if not delivery_info['deliverable']:
        return None, delivery_info.get('message', 'Delivery not available')
    
    delivery_fee = delivery_info['fee']
    
    # Coupon discount
    discount_amount = Decimal('0.00')
    coupon = None
    
    if coupon_code:
        coupon, error = validate_coupon(coupon_code, user, subtotal)
        if error:
            return None, error
        discount_amount = calculate_discount(coupon, subtotal)
    
    total_amount = subtotal + delivery_fee - discount_amount
    
    # Create order
    order = Order.objects.create(
        customer=user,
        delivery_address=address,
        status=Order.Status.PENDING,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount_amount=discount_amount,
        coupon=coupon,
        total_amount=total_amount,
        payment_method=payment_method,
        payment_status=Order.PaymentStatus.PENDING,
        special_instructions=special_instructions
    )
    
    # Create order items (snapshot current price and commission)
    for cart_item in cart_items:
        unit_price = cart_item.variant.effective_price if cart_item.variant else cart_item.product.effective_price
        commission_amount = unit_price * cart_item.quantity * cart_item.product.vendor.commission_rate / 100
        
        OrderItem.objects.create(
            order=order,
            product=cart_item.product,
            variant=cart_item.variant,
            vendor=cart_item.product.vendor,
            quantity=cart_item.quantity,
            unit_price=unit_price,
            commission_amount=commission_amount,
            item_status=OrderItem.ItemStatus.PENDING
        )
    
    # Create transaction record
    Transaction.objects.create(
        order=order,
        gateway=payment_method,
        amount=total_amount,
        status=Transaction.Status.INITIATED
    )
    
    # Clear cart
    clear_cart(user=user)
    
    # Update vendor stats
    for cart_item in cart_items:
        from apps.catalog.services import update_product_stock
        update_product_stock(cart_item.product, -cart_item.quantity, cart_item.variant)
    
    return order, None


# =============================================================================
# Order Status Management
# =============================================================================

def update_order_status(order: Order):
    """
    Recompute order status based on item statuses — production bugfix.
    Called after each item status change.
    Fixes: Order.Status.PARTIAL does not exist in model.
    """
    items = list(order.items.all())
    if not items:
        return
    
    statuses = [i.item_status for i in items]
    
    # All delivered
    if all(s == OrderItem.ItemStatus.DELIVERED for s in statuses):
        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now() if not order.delivered_at else order.delivered_at
        order.save(update_fields=['status', 'delivered_at'])
        return
    
    # All cancelled
    if all(s == OrderItem.ItemStatus.CANCELLED for s in statuses):
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        return
    
    # Any cancelled = stay at current status but track partial — map to PREPARING
    # (Order model has no PARTIAL — use PREPARING as closest in-progress state)
    if any(s == OrderItem.ItemStatus.CANCELLED for s in statuses):
        # Keep existing status unless all cancelled (handled above)
        # Optionally set a flag — for now keep CONFIRMED
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=['status'])
        return

    # Out for delivery
    if any(s == OrderItem.ItemStatus.DELIVERED for s in statuses) or any(s == 'out_for_delivery' for s in statuses):
        # If any delivered and rest preparing → OUT_FOR_DELIVERY
        order.status = Order.Status.OUT_FOR_DELIVERY
        order.save(update_fields=['status'])
        return
    
    # Preparing / Ready
    if all(s in [OrderItem.ItemStatus.PREPARING, OrderItem.ItemStatus.READY, OrderItem.ItemStatus.CONFIRMED] for s in statuses):
        # If at least one preparing
        if any(s == OrderItem.ItemStatus.PREPARING for s in statuses):
            order.status = Order.Status.PREPARING
        else:
            order.status = Order.Status.CONFIRMED
        order.save(update_fields=['status'])
        return
    
    # Confirmed
    if all(s in [OrderItem.ItemStatus.CONFIRMED, OrderItem.ItemStatus.PENDING] for s in statuses):
        if any(s == OrderItem.ItemStatus.CONFIRMED for s in statuses):
            order.status = Order.Status.CONFIRMED
            if not order.confirmed_at:
                order.confirmed_at = timezone.now()
            order.save(update_fields=['status', 'confirmed_at'])
        return
    # Fallback — keep current


@transaction.atomic
def cancel_order(order: Order, user, reason: str = None):
    """
    Cancel an order.
    Only allows cancellation if order is still pending or confirmed.
    """
    if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
        return False, "This order cannot be cancelled anymore"
    
    if order.customer != user:
        return False, "You are not authorized to cancel this order"
    
    order.status = Order.Status.CANCELLED
    order.cancellation_reason = reason or ''
    order.save(update_fields=['status', 'cancellation_reason'])
    
    # Refund if already paid
    if order.payment_status == Order.PaymentStatus.PAID:
        # Mark for refund (actual refund processed by payment gateway)
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.save(update_fields=['payment_status'])
        
        # Create refund transaction
        Transaction.objects.create(
            order=order,
            gateway=order.payment_method,
            amount=order.total_amount,
            status=Transaction.Status.REFUNDED
        )
    
    # Restore stock
    for item in order.items.all():
        from apps.catalog.services import update_product_stock
        update_product_stock(item.product, item.quantity, item.variant)
    
    return True, None


# =============================================================================
# Payment Processing
# =============================================================================

def initiate_esewa_payment(order: Order):
    """
    Initiate eSewa payment.
    Returns payment URL and reference ID.
    """
    # Placeholder for eSewa integration
    # In production, use eSewa API
    import uuid
    
    ref_id = f"MM-{order.id}-{uuid.uuid4().hex[:6].upper()}"
    
    # Update transaction
    order.transactions.update_or_create(
        gateway='esewa',
        defaults={'gateway_transaction_id': ref_id}
    )
    
    # Return eSewa payment URL
    # In production: return eSewa endpoint with appropriate parameters
    return f"https://uat.esewa.com.np/epay/transact?amt={order.total_amount}&pid={ref_id}&su=success&fu=failure"


def initiate_khalti_payment(order: Order):
    """
    Initiate Khalti payment.
    Returns payment URL and reference ID.
    """
    import uuid
    
    ref_id = f"MM-{order.id}-{uuid.uuid4().hex[:6].upper()}"
    
    order.transactions.update_or_create(
        gateway='khalti',
        defaults={'gateway_transaction_id': ref_id}
    )
    
    # Return Khalti payment URL
    return f"https://khalti.com/payment?amount={order.total_amount * 100}&product_identity={ref_id}"


@transaction.atomic
def process_payment_callback(order: Order, gateway: str, status: str, transaction_id: str):
    """
    Process payment gateway callback.
    """
    try:
        transaction = order.transactions.get(gateway=gateway)
        transaction.gateway_transaction_id = transaction_id
        transaction.status = Transaction.Status.SUCCESS if status == 'success' else Transaction.Status.FAILED
        transaction.save()
        
        if status == 'success':
            order.payment_status = Order.PaymentStatus.PAID
            order.status = Order.Status.CONFIRMED
            order.confirmed_at = timezone.now()
            order.save(update_fields=['payment_status', 'status', 'confirmed_at'])
            
            # Update vendor order counts
            for item in order.items.all():
                from apps.accounts.services import refresh_vendor_stats
                refresh_vendor_stats(item.vendor)
            
            return True
        else:
            order.payment_status = Order.PaymentStatus.FAILED
            order.save(update_fields=['payment_status'])
            return False
    except Transaction.DoesNotExist:
        return False


# =============================================================================
# Vendor Payout Services
# =============================================================================

def calculate_vendor_payout(vendor, period_start, period_end):
    """
    Calculate payout for a vendor in a given period.
    """
    items = OrderItem.objects.filter(
        vendor=vendor,
        item_status='delivered',
        order__placed_at__date__gte=period_start,
        order__placed_at__date__lte=period_end
    )
    
    gross_sales = items.aggregate(total=Sum('unit_price'))['total'] or Decimal('0.00')
    commission_deducted = items.aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
    net_payout = gross_sales - commission_deducted
    
    return {
        'gross_sales': gross_sales,
        'commission_deducted': commission_deducted,
        'net_payout': net_payout,
        'item_count': items.count(),
    }


def create_vendor_payout(vendor, period_start, period_end):
    """
    Create a vendor payout record.
    """
    calc = calculate_vendor_payout(vendor, period_start, period_end)
    
    if calc['item_count'] == 0:
        return None
    
    payout = VendorPayout.objects.create(
        vendor=vendor,
        period_start=period_start,
        period_end=period_end,
        gross_sales=calc['gross_sales'],
        commission_deducted=calc['commission_deducted'],
        net_payout=calc['net_payout'],
        status=VendorPayout.Status.PENDING
    )
    
    return payout


# =============================================================================
# Marketplace Improvement — Transparent Pricing
# =============================================================================

def calculate_transparent_pricing(subtotal, delivery_address=None, coupon_discount=Decimal('0.00')):
    """
    Transparent Pricing — display full payable amount before checkout.
    
    Returns breakdown: subtotal, tax (13% VAT Nepal), platform_fee (2%),
    shipping, discount, total_payable.
    """
    from decimal import Decimal, ROUND_HALF_UP
    
    subtotal = Decimal(str(subtotal))
    tax_rate = Decimal('13.00')  # Nepal VAT
    platform_fee_rate = Decimal('2.00')

    tax_amount = (subtotal * tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    platform_fee = (subtotal * platform_fee_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Shipping: hyperlocal tiered
    shipping_fee = Decimal('80.00')
    estimated_minutes = 180
    if delivery_address:
        try:
            delivery_info = calculate_delivery_fee(delivery_address)
            if delivery_info.get('deliverable'):
                shipping_fee = Decimal(str(delivery_info['fee']))
                estimated_minutes = delivery_info.get('estimated_minutes', 180)
        except Exception:
            pass
        # Ward-based adjustment if no zone match
        if hasattr(delivery_address, 'ward_number'):
            ward = delivery_address.ward_number
            if ward <= 5:
                shipping_fee = min(shipping_fee, Decimal('60.00'))
            elif ward <= 10:
                shipping_fee = min(shipping_fee, Decimal('80.00'))
            else:
                shipping_fee = max(shipping_fee, Decimal('120.00'))

    discount = Decimal(str(coupon_discount))
    total_payable = subtotal + tax_amount + platform_fee + shipping_fee - discount
    if total_payable < 0:
        total_payable = Decimal('0.00')

    return {
        'subtotal': float(subtotal),
        'tax_rate': float(tax_rate),
        'tax_amount': float(tax_amount),
        'platform_fee_rate': float(platform_fee_rate),
        'platform_fee': float(platform_fee),
        'shipping_fee': float(shipping_fee),
        'estimated_delivery_minutes': estimated_minutes,
        'discount': float(discount),
        'total_payable': float(total_payable),
        'currency': 'NPR',
        'breakdown_visible': True,
        'savings_vs_mrp': 0.0,
    }


def get_cart_pricing_breakdown(user=None, session_key=None, delivery_address=None, coupon_code=None):
    """Full cart pricing with transparent taxes/fees — for cart & product pages."""
    subtotal = get_cart_total(user=user, session_key=session_key)
    discount = Decimal('0.00')
    coupon = None
    if coupon_code and user:
        from .services import validate_coupon, calculate_discount
        # avoid circular import: functions defined above in same file
        coupon, err = validate_coupon(coupon_code, user, subtotal)
        if coupon and not err:
            # calculate_discount expects different signature earlier — adapt
            try:
                discount = Decimal(str(calculate_discount(coupon, float(subtotal))))
            except Exception:
                discount = Decimal('0.00')
    pricing = calculate_transparent_pricing(subtotal, delivery_address, discount)
    pricing['item_count'] = sum(i.quantity for i in get_cart_items(user=user, session_key=session_key))
    pricing['coupon'] = coupon.code if coupon else None
    return pricing


def get_product_pricing_preview(product, variant=None, delivery_ward=4):
    """Product page transparent pricing preview — Marketplace Improvement."""
    base_price = variant.effective_price if variant else product.effective_price
    tax = round(float(base_price) * 13 / 100, 2)
    platform_fee = round(float(base_price) * 2 / 100, 2)
    # shipping estimate by ward
    if delivery_ward <= 5:
        shipping = 60
    elif delivery_ward <= 10:
        shipping = 80
    else:
        shipping = 120
    total = round(float(base_price) + tax + platform_fee + shipping, 2)
    return {
        'base_price': float(base_price),
        'tax': tax,
        'platform_fee': platform_fee,
        'shipping_estimate': shipping,
        'total_payable': total,
        'you_save': round(float(product.price - product.effective_price), 2) if product.discounted_price else 0,
        'emi_available': total > 5000,
        'cod_available': True,
    }