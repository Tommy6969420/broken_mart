from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class StorefrontRoutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123",
            phone_number="9841000000",
            is_phone_verified=True,
        )

    def test_public_pages_render(self):
        public_urls = [
            ("core:home", None),
            ("core:about", None),
            ("core:contact", None),
            ("core:search_results", None),
            ("accounts:register", None),
            ("catalog:category_list", None),
            ("catalog:product_list", None),
            ("support:help_center", None),
        ]

        for name, kwargs in public_urls:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200, msg=f"{name} did not resolve 200")

    def test_authenticated_pages_render(self):
        self.client.force_login(self.user)
        auth_urls = [
            ("accounts:vendor_register", None),
            ("accounts:rider_register", None),
            ("catalog:wishlist", None),
            ("orders:cart", None),
            ("orders:order_list", None),
            ("support:complaint_form", None),
        ]

        for name, kwargs in auth_urls:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200, msg=f"{name} did not resolve 200 for auth user")
