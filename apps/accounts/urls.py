"""
URL patterns for accounts app.
"""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("verify-otp/", views.VerifyOTPView.as_view(), name="verify_otp"),
    path("resend-otp/", views.ResendOTPView.as_view(), name="resend_otp"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    
    # Profile
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("change-password/", views.ChangePasswordView.as_view(), name="change_password"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm"
    ),
    
    # Addresses
    path("addresses/", views.AddressListView.as_view(), name="address_list"),
    path("addresses/add/", views.AddressCreateView.as_view(), name="address_create"),
    path("addresses/<int:pk>/edit/", views.AddressUpdateView.as_view(), name="address_edit"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path("addresses/<int:pk>/set-default/", views.address_set_default, name="address_set_default"),
    
    # Vendor
    path("vendor/register/", views.VendorRegisterView.as_view(), name="vendor_register"),
    path("vendor/agreement/", views.VendorAgreementView.as_view(), name="vendor_agreement"),
    path("vendor/status/", views.VendorStatusView.as_view(), name="vendor_status"),
    path("vendor/dashboard/", views.VendorDashboardView.as_view(), name="vendor_dashboard"),
    path("vendor/profile/edit/", views.VendorProfileEditView.as_view(), name="vendor_profile_edit"),
    
    # Rider
    path("rider/register/", views.RiderRegisterView.as_view(), name="rider_register"),
    path("rider/dashboard/", views.RiderDashboardView.as_view(), name="rider_dashboard"),
    path("rider/profile/edit/", views.RiderProfileEditView.as_view(), name="rider_profile_edit"),
    
    # HTMX Partials
    path("partials/profile-dropdown/", views.profile_dropdown_partial, name="profile_dropdown_partial"),
]