from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.accounts.forms import AddressForm
from apps.accounts.models import Address, RiderProfile, VendorProfile
from apps.catalog.models import Category, Product, ProductVariant
from apps.delivery.models import Delivery, DeliveryZone
from apps.delivery.services import accept_delivery, assign_delivery
from apps.orders.models import Cart, CartItem
from apps.orders.services import place_order

User = get_user_model()


class DeliveryKYCAndMapTests(TestCase):
    def setUp(self):
        # Create customer
        self.customer = User.objects.create_user(
            username="ram",
            email="ram@example.com",
            password="pass",
            phone_number="9841111111",
            is_phone_verified=True,
        )
        # Create customer address in Makwanpur
        self.address = Address.objects.create(
            user=self.customer,
            label="Home",
            full_address="Main Bazaar",
            landmark="Near chowk",
            municipality=Address.Municipality.HETAUDA,
            ward_number=4,
            latitude=Decimal("27.428700"),
            longitude=Decimal("85.032000"),
            is_default=True,
        )

        # Create vendor
        self.vendor_user = User.objects.create_user(
            username="vendor",
            email="vendor@example.com",
            password="pass",
            phone_number="9842222222",
            is_phone_verified=True,
        )
        self.category = Category.objects.create(name="Grocery", slug="grocery")
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            shop_name="Makwanpur Shop",
            verification_status="verified",
            commission_rate=Decimal("5.00"),
            category=self.category,
        )
        self.product = Product.objects.create(
            vendor=self.vendor,
            category=self.category,
            name="Rice",
            slug="rice",
            price=Decimal("1000.00"),
            stock_quantity=10,
            moderation_status=Product.ModerationStatus.APPROVED,
            is_active=True,
        )

        # Create Delivery Zone
        self.zone = DeliveryZone.objects.create(
            name="Hetauda Core",
            ward_numbers=[1, 2, 3, 4, 5],
            base_delivery_fee=Decimal("50.00"),
            estimated_delivery_time_minutes=30,
            is_active=True,
        )

        # Create unverified rider
        self.unverified_rider_user = User.objects.create_user(
            username="rider_unverified",
            email="rider1@example.com",
            password="pass",
            phone_number="9843333333",
            is_phone_verified=True,
        )
        self.unverified_rider = RiderProfile.objects.create(
            user=self.unverified_rider_user,
            vehicle_type=RiderProfile.VehicleType.BIKE,
            kyc_status=RiderProfile.KYCStatus.PENDING,
            current_zone=self.zone,
        )

        # Create verified rider
        self.verified_rider_user = User.objects.create_user(
            username="rider_verified",
            email="rider2@example.com",
            password="pass",
            phone_number="9844444444",
            is_phone_verified=True,
        )
        self.verified_rider = RiderProfile.objects.create(
            user=self.verified_rider_user,
            vehicle_type=RiderProfile.VehicleType.BIKE,
            kyc_status=RiderProfile.KYCStatus.VERIFIED,
            is_available=True,
            current_zone=self.zone,
        )

    def test_order_placement_creates_unassigned_delivery(self):
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        order, error = place_order(
            user=self.customer,
            address=self.address,
            payment_method="cod",
        )
        self.assertIsNone(error)
        self.assertIsNotNone(order)

        # Verify delivery created in UNASSIGNED state
        delivery = Delivery.objects.get(order=order)
        self.assertEqual(delivery.status, Delivery.Status.UNASSIGNED)
        self.assertIsNone(delivery.rider)

    def test_unverified_rider_cannot_accept_delivery(self):
        # Create an unassigned delivery
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        order, _ = place_order(user=self.customer, address=self.address, payment_method="cod")
        delivery = Delivery.objects.get(order=order)

        success, error = accept_delivery(self.unverified_rider, delivery.id)
        self.assertFalse(success)
        self.assertIn("KYC verification required", error)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, Delivery.Status.UNASSIGNED)

    def test_verified_rider_can_accept_delivery(self):
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        order, _ = place_order(user=self.customer, address=self.address, payment_method="cod")
        delivery = Delivery.objects.get(order=order)

        success, error = accept_delivery(self.verified_rider, delivery.id)
        self.assertTrue(success)
        self.assertIsNone(error)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, Delivery.Status.ASSIGNED)
        self.assertEqual(delivery.rider, self.verified_rider)

    def test_assign_delivery_rejects_unverified_rider(self):
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        order, _ = place_order(user=self.customer, address=self.address, payment_method="cod")
        delivery = Delivery.objects.get(order=order)

        # Force is_available=True temporarily on unverified rider DB object
        RiderProfile.objects.filter(id=self.unverified_rider.id).update(is_available=True)
        self.unverified_rider.refresh_from_db()

        success, error = assign_delivery(delivery.id, self.unverified_rider.id)
        self.assertFalse(success)
        self.assertIn("not KYC verified", error)

    def test_address_form_validates_makwanpur_bounds(self):
        # Valid Makwanpur coordinates
        form_valid = AddressForm(data={
            "label": "Home",
            "full_address": "Main Road",
            "landmark": "Temple",
            "municipality": Address.Municipality.HETAUDA,
            "ward_number": 4,
            "latitude": "27.428700",
            "longitude": "85.032000",
        })
        self.assertTrue(form_valid.is_valid())

        # Invalid coordinates outside Makwanpur (e.g., Kathmandu or outside Nepal)
        form_invalid = AddressForm(data={
            "label": "Away",
            "full_address": "Kathmandu",
            "landmark": "Stupa",
            "municipality": Address.Municipality.HETAUDA,
            "ward_number": 4,
            "latitude": "27.717200",  # Outside Makwanpur max lat 27.65
            "longitude": "85.324000",
        })
        self.assertFalse(form_invalid.is_valid())
        self.assertIn("Makwanpur", str(form_invalid.errors))
