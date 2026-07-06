from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from apps.accounts.models import Address, VendorProfile
from apps.catalog.models import Category, Product
from apps.delivery.models import Delivery, DeliveryZone
from apps.orders.models import Order, OrderItem

User = get_user_model()


class OrderTimelineAndRoutingTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="ram_shopper",
            email="ram@makwanpur.test",
            password="pass",
            phone_number="+9779841000123",
            role=User.Role.CUSTOMER,
            is_phone_verified=True,
        )
        self.vendor_user = User.objects.create_user(
            username="seller_user",
            email="seller@makwanpur.test",
            password="pass",
            phone_number="+9779841000456",
            role=User.Role.VENDOR,
            is_phone_verified=True,
        )
        self.category = Category.objects.create(name="Clothing", slug="clothing")
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            shop_name="Hetauda Store",
            verification_status="verified",
            category=self.category,
        )
        self.product = Product.objects.create(
            vendor=self.vendor,
            category=self.category,
            name="Kurta",
            slug="kurta",
            price=Decimal("1500.00"),
            stock_quantity=10,
            moderation_status="approved",
            is_active=True,
        )
        self.address = Address.objects.create(
            user=self.customer,
            label="Home",
            full_address="Main Bazaar",
            municipality="Hetauda",
            ward_number=4,
            is_default=True,
        )
        self.order = Order.objects.create(
            customer=self.customer,
            delivery_address=self.address,
            status=Order.Status.CONFIRMED,
            subtotal=Decimal("1500.00"),
            delivery_fee=Decimal("60.00"),
            total_amount=Decimal("1560.00"),
            payment_method="cod",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            vendor=self.vendor,
            quantity=1,
            unit_price=Decimal("1500.00"),
            commission_amount=Decimal("75.00"),
        )
        self.delivery = Delivery.objects.create(
            order=self.order,
            status=Delivery.Status.UNASSIGNED,
            delivery_fee_owed_to_rider=Decimal("48.00"),
        )

    def test_order_timeline_view_renders(self):
        self.client.force_login(self.customer)
        res = self.client.get(reverse("orders:order_detail", kwargs={"order_id": self.order.id}))
        self.assertEqual(res.status_code, 200)
        self.assertIn("Granular Tracking", res.content.decode())

    def test_cart_and_checkout_pages_render(self):
        self.client.force_login(self.customer)
        res = self.client.get(reverse("orders:cart"))
        self.assertEqual(res.status_code, 200)

        from apps.orders.models import Cart, CartItem
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        res_checkout = self.client.get(reverse("orders:checkout"))
        self.assertEqual(res_checkout.status_code, 200)

    def test_login_role_based_routing(self):
        res = self.client.post(
            reverse("accounts:login"),
            data={"username": "seller@makwanpur.test", "password": "pass"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, reverse("accounts:vendor_dashboard"))
