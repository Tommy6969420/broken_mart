"""
Catalog domain: Category, Product, ProductVariant, ProductImage, Review, Wishlist.

Full-scale build — all spec models live. Review is linked to OrderItem
(verified purchases only), Wishlist is unique per (user, product).
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Category(models.Model):
    """Hierarchical categories (parent self-FK supports 'Clothing > Men's')."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    icon = models.ImageField(upload_to="category_icons/", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"
        indexes = [models.Index(fields=["is_active"])]

    def __str__(self):
        return f"{self.parent} > {self.name}" if self.parent else self.name


class Product(models.Model):
    """A vendor's listing.

    Stock rules: if the product has variants, per-variant ``stock_quantity``
    is authoritative and this field is ignored (enforced in
    ``apps.catalog.services.available_stock``). Vendors pause listings with
    ``is_active`` instead of deleting (order history keeps its FK).
    """

    class Condition(models.TextChoices):
        NEW = "new", "New"
        USED = "used", "Used"

    # --- Quality Control: Moderation Workflow ---
    class ModerationStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        AUTO_FLAGGED = "auto_flagged", "Auto-Flagged"
        IN_REVIEW = "in_review", "Manual Review"
        APPROVED = "approved", "Approved — Live"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    vendor = models.ForeignKey("accounts.VendorProfile", on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=64, blank=True)
    condition = models.CharField(max_length=5, choices=Condition.choices, default=Condition.NEW)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Marketplace Improvement: Quality Control / Moderation ---
    moderation_status = models.CharField(
        max_length=15,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
        db_index=True,
        help_text="Listing must be APPROVED before public visibility."
    )
    moderation_notes = models.TextField(blank=True, help_text="Reviewer notes / rejection reason.")
    flagged_reasons = models.JSONField(default=list, blank=True, help_text="Auto-flag reasons: ['prohibited_keyword', 'price_anomaly', ...]")
    auto_flag_score = models.PositiveSmallIntegerField(
        default=0,
        help_text="0-100 risk score from automated checks. >60 = auto_flagged."
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="moderated_products"
    )
    # Transparent pricing fields — cached for performance
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=13.00, help_text="Nepal VAT %")
    platform_fee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.00, help_text="Platform service fee %")

    class Meta:
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["vendor", "is_active"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["moderation_status", "is_active"]),
            models.Index(fields=["auto_flag_score"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["vendor", "slug"], name="unique_slug_per_vendor"),
            models.CheckConstraint(
                condition=models.Q(discounted_price__isnull=True) | models.Q(discounted_price__lt=models.F("price")),
                name="discount_below_price",
            ),
        ]

    @property
    def effective_price(self):
        return self.discounted_price if self.discounted_price is not None else self.price

    @property
    def has_variants(self):
        return self.variants.exists()

    # --- Transparent Pricing (Marketplace Improvement) ---
    @property
    def pricing_breakdown(self):
        """Full payable amount breakdown — Transparent Pricing improvement."""
        base = float(self.effective_price)
        tax_amount = round(base * float(self.tax_rate) / 100, 2)
        platform_fee = round(base * float(self.platform_fee_rate) / 100, 2)
        # Shipping estimate: hyperlocal Hetauda tiers
        # Ward 1-10: NPR 60-100, outside: 120-150 — simplified
        shipping_estimate = 80.0
        if hasattr(self.vendor, 'shop_ward_number'):
            ward = self.vendor.shop_ward_number or 4
            shipping_estimate = 60 if ward <= 5 else 100 if ward <= 10 else 140
        subtotal = base
        total = round(subtotal + tax_amount + platform_fee + shipping_estimate, 2)
        return {
            "base_price": base,
            "tax_rate": float(self.tax_rate),
            "tax_amount": tax_amount,
            "platform_fee_rate": float(self.platform_fee_rate),
            "platform_fee": platform_fee,
            "shipping_estimate": shipping_estimate,
            "subtotal": subtotal,
            "total_payable": total,
            "savings": round(float(self.price - self.effective_price), 2) if self.discounted_price else 0,
            "currency": "NPR",
        }

    @property
    def is_approved_and_live(self):
        """Quality Control: only APPROVED listings are publicly visible."""
        return self.moderation_status == self.ModerationStatus.APPROVED and self.is_active

    def run_automated_moderation(self):
        """Automated flagging — Quality Control improvement.
        Returns (flag_score, reasons)."""
        reasons = []
        score = 0
        text_blob = f"{self.name} {self.description} {self.sku}".lower()

        prohibited_keywords = [
            "fake", "replica 1:1", "counterfeit", "illegal", "prescription", 
            "weapon", "explosive", "drugs", "pirated", "stolen"
        ]
        for kw in prohibited_keywords:
            if kw in text_blob:
                reasons.append(f"prohibited_keyword:{kw}")
                score += 35

        # Price anomaly: >10x category avg or < NPR 10 suspicious
        try:
            from django.db.models import Avg
            cat_avg = Product.objects.filter(
                category=self.category,
                moderation_status=self.ModerationStatus.APPROVED
            ).aggregate(avg=Avg('price'))['avg'] or 1000
            if float(self.price) > float(cat_avg) * 10:
                reasons.append("price_anomaly_high")
                score += 25
            if float(self.price) < 10:
                reasons.append("price_anomaly_low")
                score += 15
        except Exception:
            pass

        # Short / spammy description
        if len(self.description.strip()) < 30:
            reasons.append("description_too_short")
            score += 20
        # ALL CAPS name
        if self.name.isupper() and len(self.name) > 5:
            reasons.append("all_caps_title")
            score += 10
        # New unverified vendor risk bump
        if hasattr(self.vendor, 'is_verified') and not self.vendor.is_verified:
            score += 15
            reasons.append("unverified_vendor")

        self.auto_flag_score = min(score, 100)
        self.flagged_reasons = reasons

        if score >= 60:
            self.moderation_status = self.ModerationStatus.AUTO_FLAGGED
        elif score >= 30:
            # still pending but flagged for faster human review
            if self.moderation_status == self.ModerationStatus.PENDING:
                pass  # keep pending, score stored
        else:
            # Auto-approve trusted sellers with clean score
            if hasattr(self.vendor, 'is_trusted_seller') and self.vendor.is_trusted_seller and score < 15:
                self.moderation_status = self.ModerationStatus.APPROVED
                from django.utils import timezone
                self.reviewed_at = timezone.now()

        return score, reasons

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Run auto-moderation on create or significant change
        if is_new or kwargs.pop('run_moderation', True):
            # don't overwrite manual decisions
            if not self.pk or Product.objects.filter(pk=self.pk, moderation_status__in=[
                Product.ModerationStatus.APPROVED,
                Product.ModerationStatus.REJECTED,
                Product.ModerationStatus.SUSPENDED
            ]).exists() is False:
                self.run_automated_moderation()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    """Size/colour variant. ``stock_quantity`` overrides the parent product's;
    ``price_override`` (nullable) replaces the parent's effective price."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=30, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "size", "color"], name="unique_variant_per_product"),
        ]

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.product.effective_price

    def __str__(self):
        bits = [b for b in (self.size, self.color) if b]
        return f"{self.product.name} ({', '.join(bits) or 'default'})"


class ProductImage(models.Model):
    """Compressed/resized server-side on upload — never trust vendor uploads."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/")
    is_primary = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"], condition=models.Q(is_primary=True), name="one_primary_image_per_product"
            )
        ]


class Review(models.Model):
    """Verified-purchase review — linked to an OrderItem, not just any user.

    One review per order item (OneToOne). ``vendor_response`` lets the vendor
    reply publicly. On save, a Celery task refreshes
    ``VendorProfile.average_rating`` (denormalized).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    order_item = models.OneToOneField("orders.OrderItem", on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    vendor_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["product", "-created_at"])]

    def __str__(self):
        return f"{self.rating}★ on {self.product}"


class Wishlist(models.Model):
    """Saved products, unique per (user, product)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_entry")]
