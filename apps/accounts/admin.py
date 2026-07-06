"""
Admin configuration for accounts app.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, RiderProfile, User, VendorProfile, SellerReview


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model."""
    
    list_display = ('email', 'username', 'role', 'is_phone_verified', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active', 'is_phone_verified', 'preferred_language')
    search_fields = ('email', 'username', 'phone_number')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal Info', {'fields': ('phone_number', 'profile_picture', 'preferred_language')}),
        ('Role & Status', {'fields': ('role', 'is_phone_verified', 'is_active')}),
        ('Permissions', {'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'phone_number', 'password1', 'password2', 'role'),
        }),
    )
    
    readonly_fields = ('date_joined', 'last_login')


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Admin for Address model."""
    
    list_display = ('label', 'user', 'municipality', 'ward_number', 'is_default')
    list_filter = ('municipality', 'is_default')
    search_fields = ('user__email', 'label', 'full_address', 'landmark')
    raw_id_fields = ('user',)


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    """Admin for VendorProfile model — Trust & Transparency enhanced."""
    
    list_display = ('shop_name', 'user', 'category', 'verification_status', 'is_trusted_seller', 'average_rating', 'trust_score', 'total_sales', 'shop_ward_number')
    list_filter = ('verification_status', 'is_trusted_seller', 'category', 'payout_method', 'shop_municipality', 'accepts_returns')
    search_fields = ('shop_name', 'shop_slug', 'user__email')
    raw_id_fields = ('user', 'category')
    readonly_fields = ('average_rating', 'total_sales', 'total_reviews_count', 'trust_score', 'agreement_signed_at', 'verified_at')
    fieldsets = (
        ('Shop Identity', {'fields': ('user', 'shop_name', 'shop_slug', 'shop_description', 'shop_logo', 'category')}),
        ('Location — Search & Discovery', {'fields': ('shop_municipality', 'shop_ward_number', 'shop_landmark', 'shop_full_address')}),
        ('Verification — Trust & Transparency', {'fields': ('verification_status', 'verified_at', 'verification_notes', 'is_trusted_seller', 'trust_score')}),
        ('Trust Metrics', {'fields': ('average_rating', 'total_sales', 'total_reviews_count')}),
        ('Return Policy — Transparent', {'fields': ('accepts_returns', 'return_window_days', 'refund_method', 'return_policy_text')}),
        ('Commercial', {'fields': ('commission_rate', 'payout_method', 'payout_account_details', 'agreement_signed_at', 'listing_fee_exempt_until')}),
    )
    actions = ['mark_verified', 'mark_trusted']

    def mark_verified(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(verification_status='verified', verified_at=timezone.now())
        self.message_user(request, f"{updated} vendors marked verified.")
    mark_verified.short_description = "✓ Mark selected vendors as VERIFIED"

    def mark_trusted(self, request, queryset):
        count = 0
        for v in queryset:
            v.update_trust_metrics()
            v.save(update_fields=['trust_score', 'is_trusted_seller'])
            count += 1
        self.message_user(request, f"Trust metrics refreshed for {count} vendors.")
    mark_trusted.short_description = "★ Recalculate trust score"


@admin.register(RiderProfile)
class RiderProfileAdmin(admin.ModelAdmin):
    """Admin for RiderProfile model."""
    
    list_display = ('__str__', 'user', 'vehicle_type', 'kyc_status', 'is_available', 'can_accept_deliveries', 'current_zone', 'total_deliveries')
    list_filter = ('kyc_status', 'vehicle_type', 'is_available', 'is_banned', 'current_zone')
    search_fields = ('user__email', 'user__username', 'citizenship_number', 'license_number')
    raw_id_fields = ('user', 'current_zone', 'kyc_verified_by')
    readonly_fields = ('total_deliveries', 'kyc_submitted_at', 'kyc_verified_at')
    actions = ['verify_kyc', 'reject_kyc']

    def verify_kyc(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            kyc_status='verified',
            kyc_verified_at=timezone.now(),
            kyc_verified_by=request.user,
            kyc_rejection_reason=''
        )
        self.message_user(request, f"{updated} riders marked KYC VERIFIED.")
    verify_kyc.short_description = "✓ Mark selected riders as KYC VERIFIED"

    def reject_kyc(self, request, queryset):
        updated = queryset.update(
            kyc_status='rejected',
            is_available=False,
            kyc_rejection_reason='Incomplete or invalid documents.'
        )
        self.message_user(request, f"{updated} riders marked KYC REJECTED.")
    reject_kyc.short_description = "✗ Mark selected riders as KYC REJECTED"


@admin.register(SellerReview)
class SellerReviewAdmin(admin.ModelAdmin):
    """Marketplace Improvement: Trust & Transparency — Seller Ratings admin."""
    list_display = ('vendor', 'reviewer', 'overall_rating', 'would_recommend', 'is_verified_purchase', 'created_at')
    list_filter = ('overall_rating', 'would_recommend', 'is_verified_purchase', 'created_at')
    search_fields = ('vendor__shop_name', 'reviewer__email', 'title', 'comment')
    raw_id_fields = ('vendor', 'reviewer', 'order')
    readonly_fields = ('created_at', 'updated_at', 'helpful_count')