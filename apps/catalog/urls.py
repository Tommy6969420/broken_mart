"""
URL patterns for catalog app.
"""
from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    # Categories
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/<slug:slug>/", views.CategoryDetailView.as_view(), name="category_detail"),
    path("categories/<int:category_id>/children/", views.category_children_partial, name="category_children"),
    
    # Products
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/<slug:slug>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("products/<int:product_id>/quick-view/", views.product_quick_view, name="product_quick_view"),
    path("products/<int:product_id>/variants/", views.product_variants_partial, name="product_variants"),
    
    # Search
    path("search/", views.product_search, name="search"),
    path("search/suggestions/", views.search_suggestions, name="search_suggestions"),
    
    # Reviews
    path("products/<slug:product_slug>/review/", views.ReviewFormView.as_view(), name="review_form"),
    
    # Wishlist
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
    path("wishlist/toggle/", views.toggle_wishlist_ajax, name="wishlist_toggle"),
    
    # Vendor Products
    path("vendor/products/", views.VendorProductListView.as_view(), name="vendor_product_list"),
    path("vendor/products/add/", views.VendorProductFormView.as_view(), name="vendor_product_create"),
    path("vendor/products/<int:product_id>/edit/", views.VendorProductFormView.as_view(), name="vendor_product_edit"),
    path("vendor/products/<int:product_id>/delete/", views.VendorProductDeleteView.as_view(), name="vendor_product_delete"),
    
    # Vendor Storefront
    path("vendor/<slug:slug>/", views.VendorStorefrontView.as_view(), name="vendor_storefront"),
]