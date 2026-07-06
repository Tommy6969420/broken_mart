from django.test import SimpleTestCase
from django.urls import reverse


class StorefrontRoutesTests(SimpleTestCase):
    def test_core_pages_render(self):
        urls = [
            ("core:home", None),
            ("core:about", None),
            ("core:contact", None),
            ("core:search_results", None),
            ("accounts:register", None),
            ("accounts:vendor_register", None),
            ("accounts:rider_register", None),
            ("catalog:category_list", None),
            ("catalog:product_list", None),
            ("catalog:wishlist", None),
            ("orders:cart", None),
            ("orders:order_list", None),
            ("support:help_center", None),
            ("support:complaint_form", None),
            ("delivery:delivery_detail", {"delivery_id": 1}),
        ]

        for name, kwargs in urls:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200, msg=f"{name} did not resolve successfully")
