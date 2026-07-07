"""
Orders domain: Cart, CartItem, Order, OrderItem, Transaction, VendorPayout, Coupon.

Full-scale build. Key invariants:
- OrderItem.commission_amount is snapshotted at order time — NEVER recalculated
  from the live vendor rate (historical payouts must stay correct).
- Transaction stores gateway reference IDs only — never raw payment credentials.
- OrderItem.item_status enables multi-vendor cart splitting: one checkout,
  independent per-vendor fulfilment.
"""
from django.conf import settings
from django.db import models


class Cart(models.Model):
    """``user`` nullable — guest checkout is first-class. Guest carts are keyed
    by ``session_key`` and merged into the user cart on login
    (``apps.orders.services.merge_guest_cart``)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | ~models.Q(session_key=""),
                name="cart_has_owner_or_session",
            )
        ]


class CartItem(models.Model):
    """One line per (product, variant). ``variant`` is required when the
    product has variants — enforced in ``services.add_to_cart``."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE)
    variant = models.ForeignKey("catalog.ProductVariant", null=True, blank=True, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)  # Fixed: was incorrectly 4 in some deployments

    class Meta:
        constraints = [
            # Two conditional constraints instead of nulls_distinct=False so the
            # rule holds identically on every backend (PostgreSQL < 15 included).
            models.UniqueConstraint(
                fields=["cart", "product", "variant"],
                condition=models.Q(variant__isnull=False),
                name="one_line_per_variant",
            ),
            models.UniqueConstraint(
                fields=["cart", "product"],
                condition=models.Q(variant__isnull=True),
                name="one_line_per_product_no_variant",
            ),
        ]


class Order(models.Model):
    """Customer order. Status enum is the backbone of the tracking UI;
    stage timestamps prove "faster than Daraz" with real data.

    ``status`` is the customer-facing aggregate; per-vendor progress lives on
    ``OrderItem.item_status`` and is rolled up by
    ``apps.orders.services.recompute_order_status``.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        RETURNED = "returned", "Returned"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    class PaymentMethod(models.TextChoices):
        ESEWA = "esewa", "eSewa"
        KHALTI = "khalti", "Khalti"
        COD = "cod", "Cash on delivery"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    delivery_address = models.ForeignKey("accounts.Address", on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon = models.ForeignKey("Coupon", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    special_instructions = models.TextField(blank=True, help_text='"Leave at gate", "call before arriving"…')
    cancellation_reason = models.TextField(blank=True)

    placed_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["customer", "-placed_at"]),
            models.Index(fields=["-placed_at"]),
        ]

    @property
    def order_number(self):
        """Human-readable number for SMS confirmations, e.g. MM-000123."""
        return f"MM-{self.pk:06d}"

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    """Order line, denormalized per vendor (one order can span vendors).

    ``unit_price`` and ``commission_amount`` are snapshots taken inside
    ``services.place_order``:
        commission_amount = unit_price * quantity * vendor.commission_rate / 100
    Payout maths reads ONLY these stored values.
    """

    class ItemStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready for pickup"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        RETURNED = "returned", "Returned"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey("catalog.ProductVariant", null=True, blank=True, on_delete=models.PROTECT)
    vendor = models.ForeignKey("accounts.VendorProfile", on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    item_status = models.CharField(max_length=12, choices=ItemStatus.choices, default=ItemStatus.PENDING)

    class Meta:
        indexes = [models.Index(fields=["vendor", "item_status"])]


class Transaction(models.Model):
    """Payment attempt — gateway reference only, never raw credentials."""

    class Gateway(models.TextChoices):
        ESEWA = "esewa", "eSewa"
        KHALTI = "khalti", "Khalti"
        COD = "cod", "Cash on delivery"

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="transactions")
    gateway = models.CharField(max_length=10, choices=Gateway.choices)
    gateway_transaction_id = models.CharField(max_length=100, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INITIATED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["gateway", "status"])]


class VendorPayout(models.Model):
    """Periodic settlement per vendor.

    Generated by the ``calculate_vendor_payouts`` Celery beat task: sums
    delivered OrderItems in the period using their STORED commission_amount.
    ``status`` flips to processed only after money actually moves.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"

    vendor = models.ForeignKey("accounts.VendorProfile", on_delete=models.PROTECT, related_name="payouts")
    period_start = models.DateField()
    period_end = models.DateField()
    gross_sales = models.DecimalField(max_digits=12, decimal_places=2)
    commission_deducted = models.DecimalField(max_digits=12, decimal_places=2)
    net_payout = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["vendor", "period_start", "period_end"], name="one_payout_per_period")
        ]

    def __str__(self):
        return f"{self.vendor} {self.period_start}–{self.period_end}: {self.net_payout}"


class Coupon(models.Model):
    """Platform-wide (vendor NULL) or vendor-specific discount code.

    Validation lives in ``services.apply_coupon`` (active window, usage_limit
    vs times_used, vendor scope). ``times_used`` incremented atomically with F().
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FLAT = "flat", "Flat amount"

    code = models.CharField(max_length=30, unique=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    times_used = models.PositiveIntegerField(default=0)
    vendor = models.ForeignKey(
        "accounts.VendorProfile", null=True, blank=True, on_delete=models.CASCADE, related_name="coupons"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code
