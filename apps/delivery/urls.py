"""
URL patterns for delivery app.
"""
from django.urls import path

from . import views

app_name = "delivery"

urlpatterns = [
    # Customer delivery tracking
    path("deliveries/<int:delivery_id>/", views.DeliveryDetailView.as_view(), name="delivery_detail"),
    path("deliveries/<int:delivery_id>/tracking/", views.delivery_tracking_partial, name="delivery_tracking"),
    
    # Rider deliveries
    path("rider-deliveries/", views.RiderDeliveryListView.as_view(), name="rider_delivery_list"),
    path("rider-deliveries/<int:delivery_id>/accept/", views.rider_accept_delivery, name="rider_accept"),
    path("rider-deliveries/<int:delivery_id>/status/", views.rider_update_status, name="rider_update_status"),
    path("rider-deliveries/toggle-availability/", views.toggle_availability, name="toggle_availability"),
    path("rider-deliveries/<int:delivery_id>/card/", views.rider_delivery_card_partial, name="rider_delivery_card"),
    
    # Admin delivery management
    path("admin/deliveries/", views.AdminDeliveryListView.as_view(), name="admin_delivery_list"),
    path("admin/deliveries/<int:delivery_id>/assign/", views.admin_assign_delivery, name="admin_assign_delivery"),
    
    # Zone management
    path("admin/zones/", views.DeliveryZoneListView.as_view(), name="zone_list"),
    path("admin/zones/add/", views.DeliveryZoneCreateView.as_view(), name="zone_create"),
    path("admin/zones/<int:zone_id>/edit/", views.DeliveryZoneEditView.as_view(), name="zone_edit"),
]