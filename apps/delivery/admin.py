"""
Admin configuration for delivery app.
"""
from django.contrib import admin

from .models import Delivery, DeliveryZone


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    """Admin for DeliveryZone model."""
    
    list_display = ('name', 'ward_numbers_display', 'base_delivery_fee', 
                    'estimated_delivery_time_minutes', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    
    def ward_numbers_display(self, obj):
        return ', '.join(str(w) for w in obj.ward_numbers)
    ward_numbers_display.short_description = 'Wards'


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    """Admin for Delivery model."""
    
    list_display = ('__str__', 'order', 'rider', 'status', 'assigned_at', 'delivered_at')
    list_filter = ('status', 'rider')
    search_fields = ('order__order_number', 'rider__user__email')
    raw_id_fields = ('order', 'rider')
    readonly_fields = ('assigned_at', 'picked_up_at', 'delivered_at')
    
    fieldsets = (
        (None, {'fields': ('order', 'rider', 'status')}),
        ('Fee', {'fields': ('delivery_fee_owed_to_rider',)}),
        ('Timestamps', {'fields': ('assigned_at', 'picked_up_at', 'delivered_at')}),
        ('Failure', {'fields': ('failure_reason',)}),
    )