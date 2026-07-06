"""
URL patterns for orders app.
"""
from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    # Cart
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/add/", views.add_to_cart_ajax, name="cart_add"),
    path("cart/update/", views.update_cart_item_ajax, name="cart_update"),
    path("cart/remove/<int:item_id>/", views.remove_cart_item_ajax, name="cart_remove"),
    path("cart/clear/", views.clear_cart_ajax, name="cart_clear"),
    path("cart/item/<int:item_id>/", views.cart_item_partial, name="cart_item_partial"),
    path("cart/coupon/apply/", views.apply_coupon_ajax, name="apply_coupon"),
    
    # Checkout
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("checkout/delivery-fee/<int:address_id>/", views.delivery_fee_partial, name="delivery_fee"),
    
    # Payment
    path("payment/redirect/<int:order_id>/", views.PaymentRedirectView.as_view(), name="payment_redirect"),
    path("payment/failed/", views.PaymentFailedView.as_view(), name="payment_failed"),
    
    # Orders
    path("confirmation/<int:order_id>/", views.OrderConfirmationView.as_view(), name="order_confirmation"),
    path("orders/", views.OrderListView.as_view(), name="order_list"),
    path("orders/<int:order_id>/", views.OrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:order_id>/status/", views.order_status_partial, name="order_status"),
    path("orders/<int:order_id>/cancel/", views.OrderCancelView.as_view(), name="order_cancel"),
    path("orders/<int:order_id>/return/", views.ReturnRequestView.as_view(), name="return_request"),
    
    # Vendor Orders
    path("vendor/orders/", views.VendorOrderListView.as_view(), name="vendor_order_list"),
    path("vendor/orders/<int:order_id>/", views.VendorOrderDetailView.as_view(), name="vendor_order_detail"),
    path("vendor/orders/item/<int:item_id>/status/", views.update_item_status_ajax, name="update_item_status"),
    path("vendor/earnings/", views.VendorEarningsView.as_view(), name="vendor_earnings"),
]