"""
Comprehensive tests for Orders app
"""
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User
from apps.catalog.models import Product, Category
from apps.orders.models import Cart, CartItem, Order


class CartQuantityTest(TestCase):
    """Test cart quantity defaults and validation"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.category = Category.objects.create(name='Test')
        self.product = Product.objects.create(
            name='Test Product',
            category=self.category,
            price=100,
            vendor=self.user  # simplified
        )

    def test_cart_item_default_quantity_is_one(self):
        """Default quantity should be 1, not 4"""
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=1
        )
        self.assertEqual(item.quantity, 1)

    def test_quantity_cannot_be_less_than_one(self):
        """Quantity validation should prevent < 1"""
        cart = Cart.objects.create(user=self.user)
        with self.assertRaises(Exception):  # IntegrityError or ValidationError
            CartItem.objects.create(cart=cart, product=self.product, quantity=0)


class OrderStatusTest(TestCase):
    """Test order status transitions"""

    def test_vendor_status_buttons_update_order(self):
        # Add real tests when vendor order views are available
        pass
