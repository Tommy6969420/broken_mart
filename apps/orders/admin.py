"""
Admin configuration for orders app.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Cart, CartItem, Coupon, Order, OrderItem, Transaction, VendorPayout


class OrderItemInline(admin.TabularInline):
    """Inline for OrderItem."""
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'variant', 'vendor', 'unit_price', 'commission_amount')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin for Order model."""
    
    list_display = ('order_number', 'customer', 'status', 'payment_status', 'total_amount', 'placed_at')
    list_filter = ('status', 'payment_status', 'payment_method')
    search_fields = ('order_number', 'customer__email')
    raw_id_fields = ('customer', 'delivery_address', 'coupon')
    readonly_fields = ('order_number', 'placed_at', 'confirmed_at', 'delivered_at')
    inlines = [OrderItemInline]
    
    fieldsets = (
        (None, {'fields': ('order_number', 'customer', 'delivery_address')}),
        ('Status', {'fields': ('status', 'payment_status', 'payment_method')}),
        ('Amounts', {'fields': ('subtotal', 'delivery_fee', 'discount_amount', 'total_amount')}),
        ('Notes', {'fields': ('special_instructions', 'cancellation_reason')}),
        ('Timestamps', {'fields': ('placed_at', 'confirmed_at', 'delivered_at')}),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Admin for OrderItem model."""
    
    list_display = ('order', 'product', 'vendor', 'quantity', 'unit_price', 'item_status')
    list_filter = ('item_status', 'vendor')
    search_fields = ('order__order_number', 'product__name')
    raw_id_fields = ('order', 'product', 'variant', 'vendor')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Admin for Cart model."""
    
    list_display = ('id', 'user', 'session_key', 'created_at', 'updated_at')
    search_fields = ('user__email', 'session_key')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """Admin for CartItem model."""
    
    list_display = ('cart', 'product', 'variant', 'quantity')
    raw_id_fields = ('cart', 'product', 'variant')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin for Transaction model."""
    
    list_display = ('order', 'gateway', 'amount', 'status', 'created_at')
    list_filter = ('gateway', 'status')
    search_fields = ('order__order_number', 'gateway_transaction_id')
    raw_id_fields = ('order',)
    readonly_fields = ('created_at',)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    """Admin for Coupon model."""
    
    list_display = ('code', 'discount_type', 'value', 'usage_limit', 
                    'times_used', 'is_active', 'valid_from', 'valid_until')
    list_filter = ('is_active', 'discount_type')
    search_fields = ('code',)
    readonly_fields = ('times_used',)
    
    fieldsets = (
        (None, {'fields': ('code', 'vendor', 'is_active')}),
        ('Discount', {'fields': ('discount_type', 'value')}),
        ('Validity', {'fields': ('valid_from', 'valid_until')}),
        ('Usage', {'fields': ('usage_limit', 'times_used')}),
    )


@admin.register(VendorPayout)
class VendorPayoutAdmin(admin.ModelAdmin):
    """Admin for VendorPayout model."""
    
    list_display = ('vendor', 'period_start', 'period_end', 'gross_sales', 
                    'commission_deducted', 'net_payout', 'status')
    list_filter = ('status',)
    search_fields = ('vendor__shop_name',)
    raw_id_fields = ('vendor',)
    readonly_fields = ('period_start', 'period_end', 'gross_sales', 'commission_deducted', 'net_payout')