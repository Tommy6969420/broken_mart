"""
Accounts domain: User, Address, VendorProfile, RiderProfile.

Full-scale build — all fields from the system-design spec are live
(P1 + P2 + P3). See docs/CHANGES.md for what was un-gated and why.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    """Custom user — email login, Nepali phone number, role-based access.

    ``email`` is the USERNAME_FIELD (primary login + notification channel).
    ``phone_number`` is unique and OTP-verified at signup — in Nepal phone
    is often more reliable than email and is the delivery contact.
    ``is_active`` doubles as the soft-ban switch (never delete accounts).
    """

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        VENDOR = "vendor", "Vendor"
        RIDER = "rider", "Rider"
        ADMIN = "admin", "Admin"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        NEPALI = "ne", "नेपाली"

    email = models.EmailField(unique=True)
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[RegexValidator(r"^\+?977?9\d{9}$", "Enter a valid Nepali mobile number.")],
        help_text="Used for SMS notifications and OTP.",
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    is_phone_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True)
    preferred_language = models.CharField(max_length=2, choices=Language.choices, default=Language.ENGLISH)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "phone_number"]

    class Meta:
        indexes = [models.Index(fields=["role", "is_active"])]

    def __str__(self):
        return f"{self.email} ({self.role})"


class Address(models.Model):
    """Delivery address — landmark-first, ward-based (no formal street addressing).

    ``latitude``/``longitude`` feed map-based delivery-zone logic; nullable
    because most addresses are entered without coordinates.
    """
    class Municipality(models.TextChoices):
        HETAUDA = "Hetauda", "hetauda"
        BAGMATI = "Bagmati", "bagmati"
        BAKAIYA = "Bakaiya", "bakaiya"
        THAHA = "Thaha", "thaha"
        MAKWANPUR_GADHI = "Makwanpur Gadhi", "makwanpur gadhi"
        MANAHARI = "Manahari", "manahari"
        BHIMPHEDI = "Bhimphedi", "bhimphedi"
        INDRASAROBAR = "Indrasarobar", "indrasarobar"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50, help_text='e.g. "Home", "Shop"')
    full_address = models.TextField()
    landmark = models.TextField(blank=True, help_text="Nearby landmark — often more useful than street address.")
    municipality = models.CharField(max_length=100, choices=Municipality.choices)
    ward_number = models.PositiveSmallIntegerField()
    is_default = models.BooleanField(default=False)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name_plural = "addresses"
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(is_default=True), name="one_default_address_per_user"
            )
        ]

    def __str__(self):
        return f"{self.label} — ward {self.ward_number} ({self.user})"


class VendorProfile(models.Model):
    """Vendor shop profile, verification state, and commercial terms.

    INVARIANT: ``commission_rate`` is the *live* rate. It is snapshotted onto
    ``OrderItem.commission_amount`` at order time and never re-read for
    historical orders — changing this rate must never rewrite past payouts.

    ``average_rating`` / ``total_sales`` are denormalized caches maintained by
    ``apps.accounts.services.refresh_vendor_stats`` (called from a Celery task
    on review creation / order delivery) — never computed per page load.
    """

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class PayoutMethod(models.TextChoices):
        ESEWA = "esewa", "eSewa"
        KHALTI = "khalti", "Khalti"
        BANK = "bank", "Bank transfer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor_profile")
    shop_name = models.CharField(max_length=120)
    shop_slug = models.SlugField(max_length=140, unique=True)
    shop_description = models.TextField(blank=True)
    shop_logo = models.ImageField(upload_to="shop_logos/", blank=True)
    category = models.ForeignKey(
        "catalog.Category", on_delete=models.PROTECT, related_name="vendors",
        help_text="Primary category the vendor sells in.",
    )
    # --- Location fields for Search & Discovery (Marketplace Improvement) ---
    shop_municipality = models.CharField(
        max_length=100,
        choices=Address.Municipality.choices,
        default=Address.Municipality.HETAUDA,
        help_text="Shop physical municipality for location-based search."
    )
    shop_ward_number = models.PositiveSmallIntegerField(
        default=4,
        help_text="Hetauda ward number for hyperlocal discovery."
    )
    shop_landmark = models.CharField(max_length=200, blank=True, help_text="Nearby landmark for pickup/returns.")
    shop_full_address = models.TextField(blank=True, help_text="Full shop address for customers.")

    verification_status = models.CharField(
        max_length=10, choices=VerificationStatus.choices, default=VerificationStatus.PENDING,
        help_text="Set to 'verified' after manual vetting.",
    )
    verified_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when verification was granted.")
    verification_notes = models.TextField(blank=True, help_text="Internal notes from verification team.")
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        help_text="Per-vendor rate (%). Snapshotted onto OrderItem at order time.",
    )
    agreement_signed_at = models.DateTimeField(null=True, blank=True)
    listing_fee_exempt_until = models.DateField(
        null=True, blank=True, help_text='Implements the "free first year" policy.'
    )
    payout_method = models.CharField(max_length=10, choices=PayoutMethod.choices)
    # SECURITY: swap to EncryptedTextField (django-encrypted-model-fields) before
    # storing real account numbers. Kept as TextField so the scaffold runs without
    # a FIELD_ENCRYPTION_KEY; the swap is a one-line change + migration.
    payout_account_details = models.TextField(help_text="ENCRYPT AT REST in production.")
    # --- Trust & Transparency metrics ---
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_sales = models.PositiveIntegerField(default=0)
    total_reviews_count = models.PositiveIntegerField(default=0, help_text="Denormalized seller review count.")
    trust_score = models.PositiveSmallIntegerField(
        default=0,
        help_text="0-100 composite trust score: verification + rating + sales + response time."
    )
    is_trusted_seller = models.BooleanField(
        default=False,
        help_text="Auto-calculated: verified + rating>=4.2 + sales>=50"
    )
    # --- Return / Refund Policy (Transparent per vendor) ---
    return_window_days = models.PositiveSmallIntegerField(
        default=3,
        help_text="Return window in days, displayed on every product page."
    )
    return_policy_text = models.TextField(
        default="3-Day Doorstep Replacement: If the size does not fit or the fabric has any manufacturing defect, notify us within 3 days. Our local rider will pick up the item and deliver your replacement at your doorstep, or you can exchange directly at our physical stall.",
        help_text="Vendor-specific return policy — shown transparently on every product page."
    )
    accepts_returns = models.BooleanField(default=True)
    refund_method = models.CharField(
        max_length=20,
        choices=[("replacement", "Replacement"), ("refund", "Full Refund"), ("store_credit", "Store Credit"), ("both", "Refund or Replacement")],
        default="both"
    )

    class Meta:
        indexes = [
            models.Index(fields=["verification_status"]),
            models.Index(fields=["shop_municipality", "shop_ward_number"]),
            models.Index(fields=["average_rating", "-total_sales"]),
            models.Index(fields=["is_trusted_seller"]),
        ]

    @property
    def is_verified(self):
        return self.verification_status == self.VerificationStatus.VERIFIED

    @property
    def verified_badge_data(self):
        """Dynamic verified seller badge — Trust & Transparency improvement.
        Returns dict only if verified, else None. Templates check this."""
        if not self.is_verified:
            return None
        return {
            "label": "Verified Vendor",
            "verified_at": self.verified_at,
            "trust_score": self.trust_score,
            "rating": float(self.average_rating),
            "total_sales": self.total_sales,
            "badge_class": "bg-brand-indigo text-white",
            "icon": "✓",
        }

    @property
    def seller_rating_stars(self):
        """Return star breakdown for UI."""
        rating = float(self.average_rating)
        full = int(rating)
        half = 1 if rating - full >= 0.5 else 0
        empty = 5 - full - half
        return {"full": range(full), "half": half, "empty": range(empty), "rating": rating}

    @property
    def location_display(self):
        return f"Ward #{self.shop_ward_number}, {self.get_shop_municipality_display()}"

    def update_trust_metrics(self):
        """Recalculate trust_score and is_trusted_seller — called post-review."""
        # trust_score = weighted composite
        base = 30 if self.is_verified else 0
        rating_component = min(float(self.average_rating) * 12, 40)  # 5*12=60 capped 40
        sales_component = min(self.total_sales / 10, 20)  # 200 sales = full
        reviews_component = min(self.total_reviews_count, 10)  # up to 10 pts
        self.trust_score = int(base + rating_component + sales_component + reviews_component)
        self.is_trusted_seller = (
            self.is_verified and 
            float(self.average_rating) >= 4.2 and 
            self.total_sales >= 50
        )
        # avoid recursion: caller saves

    def __str__(self):
        return self.shop_name


class RiderProfile(models.Model):
    """Delivery rider — availability toggled by the rider from their panel.

    ``total_deliveries`` is denormalized, incremented in
    ``apps.delivery.services.complete_delivery`` inside the same transaction
    that marks the Delivery delivered.

    KYC VERIFICATION — Marketplace Improvement #6:
    Riders must complete KYC before they can accept delivery tasks.
    """

    class VehicleType(models.TextChoices):
        BIKE = "bike", "Bike"
        BICYCLE = "bicycle", "Bicycle"
        ON_FOOT = "on_foot", "On foot"

    class KYCStatus(models.TextChoices):
        NOT_SUBMITTED = "not_submitted", "KYC Not Submitted"
        PENDING = "pending", "Pending Verification"
        IN_REVIEW = "in_review", "In Review"
        VERIFIED = "verified", "KYC Verified"
        REJECTED = "rejected", "KYC Rejected"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rider_profile")
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices)
    is_available = models.BooleanField(default=False)
    current_zone = models.ForeignKey(
        "delivery.DeliveryZone", null=True, blank=True, on_delete=models.SET_NULL, related_name="riders"
    )
    total_deliveries = models.PositiveIntegerField(default=0)

    # --- KYC Verification — Production requirement #6 ---
    kyc_status = models.CharField(
        max_length=15,
        choices=KYCStatus.choices,
        default=KYCStatus.NOT_SUBMITTED,
        db_index=True,
        help_text="Rider must be KYC VERIFIED before accepting delivery tasks."
    )
    # Nepal KYC documents
    citizenship_number = models.CharField(
        max_length=30, blank=True,
        help_text="Nepal Citizenship No. — e.g. 27-01-76-12345"
    )
    citizenship_front_image = models.ImageField(
        upload_to='rider_kyc/citizenship/', blank=True,
        help_text="Citizenship front — encrypted at rest in production"
    )
    citizenship_back_image = models.ImageField(
        upload_to='rider_kyc/citizenship/', blank=True
    )
    license_number = models.CharField(
        max_length=30, blank=True,
        help_text="Driving license No. — required for BIKE vehicle_type"
    )
    license_image = models.ImageField(
        upload_to='rider_kyc/license/', blank=True
    )
    vehicle_registration_number = models.CharField(
        max_length=20, blank=True,
        help_text="e.g. Ba 19 Pa 1234 — Nepal number plate"
    )
    vehicle_bluebook_image = models.ImageField(
        upload_to='rider_kyc/bluebook/', blank=True,
        help_text="Vehicle registration (bluebook)"
    )
    selfie_with_id = models.ImageField(
        upload_to='rider_kyc/selfie/', blank=True,
        help_text="Liveness check — selfie holding citizenship"
    )
    # contact / emergency
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True)
    # Address proof — Makwanpur local
    permanent_address = models.TextField(
        blank=True,
        help_text="Permanent address as per citizenship"
    )
    current_municipality = models.CharField(
        max_length=100,
        choices=Address.Municipality.choices,
        default=Address.Municipality.HETAUDA
    )
    current_ward = models.PositiveSmallIntegerField(default=4)

    # KYC review
    kyc_submitted_at = models.DateTimeField(null=True, blank=True)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    kyc_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_riders'
    )
    kyc_rejection_reason = models.TextField(blank=True)

    # Operational safety
    is_banned = models.BooleanField(default=False)
    ban_reason = models.TextField(blank=True)
    average_delivery_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_ratings = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["is_available"]),
            models.Index(fields=["kyc_status", "is_available"]),
            models.Index(fields=["current_zone", "is_available"]),
        ]

    @property
    def is_kyc_verified(self):
        return self.kyc_status == self.KYCStatus.VERIFIED and not self.is_banned

    @property
    def can_accept_deliveries(self):
        """KYC gate — riders can ONLY take tasks after being verified."""
        return (
            self.is_kyc_verified
            and self.user.is_active
            and self.user.is_phone_verified
            and not self.is_banned
        )

    def clean(self):
        from django.core.exceptions import ValidationError
        # Enforce: is_available can only be True if KYC verified
        if self.is_available and not self.can_accept_deliveries:
            raise ValidationError(
                "KYC verification required before going online. "
                f"Current KYC status: {self.get_kyc_status_display()}. "
                "Please upload citizenship, license, and vehicle documents."
            )

    def save(self, *args, **kwargs):
        # Auto-disable availability if KYC lapses
        if self.is_available and not self.can_accept_deliveries:
            self.is_available = False
        super().save(*args, **kwargs)

    def __str__(self):
        kyc_badge = "✓" if self.is_kyc_verified else "⏳"
        return f"{kyc_badge} Rider {self.user.username} ({self.vehicle_type}) — {self.get_kyc_status_display()}"


# =============================================================================
# Marketplace Improvements — Trust & Transparency
# Seller Ratings / Reviews (separate from product reviews)
# =============================================================================

class SellerReview(models.Model):
    """
    Seller-level ratings & reviews — Trust & Transparency improvement.
    
    Distinct from catalog.Review (which is product + order_item verified).
    SellerReview aggregates vendor service quality: communication,
    shipping speed, return handling, overall trust.
    
    Linked to an Order to ensure verified-purchase only, but rates the SELLER,
    not the product.
    """

    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.CASCADE,
        related_name="seller_reviews"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="given_seller_reviews"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="seller_reviews",
        help_text="Verified purchase link — prevents fake seller reviews."
    )
    # Multi-dimension rating for transparency
    communication_rating = models.PositiveSmallIntegerField(
        default=5,
        help_text="1-5: seller communication responsiveness"
    )
    shipping_speed_rating = models.PositiveSmallIntegerField(
        default=5,
        help_text="1-5: delivery speed vs promise"
    )
    product_accuracy_rating = models.PositiveSmallIntegerField(
        default=5,
        help_text="1-5: product matched description"
    )
    overall_rating = models.PositiveSmallIntegerField(
        help_text="1-5 overall seller rating"
    )
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(blank=True)
    would_recommend = models.BooleanField(default=True)
    is_verified_purchase = models.BooleanField(default=True)
    vendor_response = models.TextField(blank=True)
    vendor_responded_at = models.DateTimeField(null=True, blank=True)
    helpful_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["vendor", "-created_at"]),
            models.Index(fields=["overall_rating"]),
            models.Index(fields=["is_verified_purchase"]),
        ]
        constraints = [
            # One seller review per order per reviewer — prevents spam
            models.UniqueConstraint(
                fields=["vendor", "reviewer", "order"],
                name="unique_seller_review_per_order",
                condition=models.Q(order__isnull=False)
            )
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # auto-calc overall if not set
        if not self.overall_rating:
            self.overall_rating = round(
                (self.communication_rating + self.shipping_speed_rating + self.product_accuracy_rating) / 3
            )
        super().save(*args, **kwargs)
        # Update vendor denormalized stats
        self._update_vendor_stats()

    def _update_vendor_stats(self):
        from django.db.models import Avg, Count
        agg = SellerReview.objects.filter(vendor=self.vendor).aggregate(
            avg=Avg("overall_rating"),
            cnt=Count("id")
        )
        self.vendor.average_rating = round(agg["avg"] or 0, 2)
        self.vendor.total_reviews_count = agg["cnt"] or 0
        self.vendor.update_trust_metrics()
        self.vendor.save(update_fields=[
            "average_rating", "total_reviews_count", "trust_score", "is_trusted_seller"
        ])

    def __str__(self):
        return f"{self.overall_rating}★ {self.vendor.shop_name} by {self.reviewer.email}"
