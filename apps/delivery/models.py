"""
Delivery domain: DeliveryZone, Delivery — fully live in the scalable build.

Zone-based fee calculation: ``apps.orders.services.calculate_delivery_fee``
resolves the customer's ward_number to a DeliveryZone and uses its
``base_delivery_fee`` / ``estimated_delivery_time_minutes`` (shown BEFORE
checkout, per the UX spec).
"""
from django.db import models


class DeliveryZone(models.Model):
    """A group of wards sharing a delivery fee and time estimate."""

    name = models.CharField(max_length=80)
    ward_numbers = models.JSONField(default=list, help_text="e.g. [1, 2, 3]")
    base_delivery_fee = models.DecimalField(max_digits=8, decimal_places=2)
    estimated_delivery_time_minutes = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Delivery(models.Model):
    """Delivery job for an order. Manual-assist assignment: the system suggests
    available riders in the zone, a human (or the rider) confirms.

    ``complete_delivery`` service marks delivered_at, increments the rider's
    denormalized total_deliveries, and (for COD) flips Order.payment_status.
    """

    class Status(models.TextChoices):
        UNASSIGNED = "unassigned", "Unassigned"
        ASSIGNED = "assigned", "Assigned"
        PICKED_UP = "picked_up", "Picked up"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="delivery")
    rider = models.ForeignKey(
        "accounts.RiderProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UNASSIGNED)
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_fee_owed_to_rider = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    failure_reason = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "deliveries"
        indexes = [models.Index(fields=["status"]), models.Index(fields=["rider", "status"])]

    def __str__(self):
        return f"Delivery for {self.order} [{self.status}]"
