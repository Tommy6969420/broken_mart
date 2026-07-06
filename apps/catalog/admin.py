"""
Admin configuration for catalog app.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Product, ProductImage, ProductVariant, Review, Wishlist


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin for Category model."""
    
    list_display = ('name', 'parent', 'is_active', 'product_count')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    
    def product_count(self, obj):
        return obj.products.filter(is_active=True).count()
    product_count.short_description = 'Products'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin for Product model."""
    
    list_display = ('name', 'vendor', 'category', 'effective_price', 'stock_display', 'is_active', 'created_at')
    list_filter = ('is_active', 'condition', 'category', 'vendor')
    search_fields = ('name', 'slug', 'sku', 'vendor__shop_name')
    raw_id_fields = ('vendor', 'category')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('vendor', 'category', 'name', 'slug')}),
        ('Pricing & Stock', {'fields': ('price', 'discounted_price', 'stock_quantity', 'sku')}),
        ('Details', {'fields': ('description', 'condition')}),
        ('Status', {'fields': ('is_active',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    def effective_price(self, obj):
        return f"NPR {obj.effective_price}"
    effective_price.short_description = 'Price'
    
    def stock_display(self, obj):
        if obj.has_variants:
            total = obj.variants.aggregate(total=models.Sum('stock_quantity'))['total'] or 0
            return format_html(f'<span class="text-blue-600">{total} (variants)</span>')
        color = 'green' if obj.stock_quantity > 5 else ('orange' if obj.stock_quantity > 0 else 'red')
        return format_html(f'<span class="text-{color}-600">{obj.stock_quantity}</span>')
    stock_display.short_description = 'Stock'


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    """Admin for ProductVariant model."""
    
    list_display = ('product', 'size', 'color', 'stock_quantity', 'effective_price')
    list_filter = ('size', 'color')
    search_fields = ('product__name',)
    raw_id_fields = ('product',)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Admin for ProductImage model."""
    
    list_display = ('product', 'image', 'is_primary', 'order')
    list_filter = ('is_primary',)
    raw_id_fields = ('product',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Admin for Review model."""
    
    list_display = ('product', 'rating', 'order_item', 'created_at')
    list_filter = ('rating',)
    search_fields = ('product__name', 'order_item__order__order_number')
    raw_id_fields = ('product', 'order_item')
    readonly_fields = ('created_at',)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    """Admin for Wishlist model."""
    
    list_display = ('user', 'product', 'added_at')
    search_fields = ('user__email', 'product__name')
    raw_id_fields = ('user', 'product')
    readonly_fields = ('added_at',)


# Import models for aggregate
from django.db import models