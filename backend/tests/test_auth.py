"""Authentication API tests (Spec 02)."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User

from .helpers import make_user


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register(self):
        resp = self.client.post(
            "/api/v1/auth/register/",
            {"email": "new@example.com", "username": "newuser", "password": "Strongpass123!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", resp.data)
        self.assertEqual(resp.data["user"]["email"], "new@example.com")
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

    def test_register_duplicate_email_rejected(self):
        self.client.post(
            "/api/v1/auth/register/",
            {"email": "dup@example.com", "username": "dup1", "password": "Strongpass123!"},
            format="json",
        )
        resp = self.client.post(
            "/api/v1/auth/register/",
            {"email": "DUP@example.com", "username": "dup2", "password": "Strongpass123!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_and_me(self):
        user, _ = make_user()
        resp = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "Testpass123!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        token = resp.data["token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        me = self.client.get("/api/v1/me/")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], user.email)

    def test_me_requires_auth(self):
        resp = self.client.get("/api/v1/me/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout(self):
        user, _ = make_user()
        resp = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "Testpass123!"},
            format="json",
        )
        token = resp.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        out = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(out.status_code, status.HTTP_200_OK)
        # Token should be gone now
        me = self.client.get("/api/v1/me/")
        self.assertEqual(me.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_seller_profile_created_via_post(self):
        # A bare user WITHOUT a seller profile: POST creates one (201).
        user = User.objects.create_user(
            username="bare", email="bare@example.com", password="Testpass123!"
        )
        self.client.force_authenticate(user=user)
        resp = self.client.post(
            "/api/v1/me/seller/",
            {"display_name": "Demo Seller"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertRegex(resp.data["seller_code"], r"^SELLER-")
        self.assertEqual(resp.data["display_name"], "Demo Seller")

    def test_seller_profile_post_is_idempotent(self):
        user, _ = make_user()
        self.client.force_authenticate(user=user)
        r1 = self.client.post("/api/v1/me/seller/", {"display_name": "A"}, format="json")
        r2 = self.client.post("/api/v1/me/seller/", {"display_name": "A"}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.data["seller_code"], r2.data["seller_code"])

    def test_health_endpoint(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "ok")