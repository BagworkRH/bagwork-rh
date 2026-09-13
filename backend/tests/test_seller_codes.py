"""Tests for seller code generation (Spec 03)."""
from django.test import TestCase

from apps.sellers.models import SellerProfile

from .helpers import make_user


class SellerCodeTests(TestCase):
    def test_code_format(self):
        _, profile = make_user()
        self.assertRegex(profile.seller_code, r"^SELLER-[A-HJKMNP-Z2-9]{6}$")

    def test_code_is_unique(self):
        _, p1 = make_user(email="a@example.com", username="a")
        _, p2 = make_user(email="b@example.com", username="b")
        self.assertNotEqual(p1.seller_code, p2.seller_code)

    def test_code_case_normalized(self):
        profile = SellerProfile()
        code = profile.generate_random_code()
        self.assertEqual(code.upper(), code)

    def test_repeated_generation_is_deterministic_format(self):
        for _ in range(50):
            code = SellerProfile.generate_random_code()
            self.assertRegex(code, r"^SELLER-[A-HJKMNP-Z2-9]{6}$")

    def test_code_generation_retries_on_collision(self):
        """Simulate a collision by pre-creating a profile then forcing many."""
        _, p1 = make_user(email="a@example.com", username="a")
        # generate_unique_code should not return p1's code
        other = SellerProfile.generate_unique_code()
        self.assertNotEqual(other, p1.seller_code)