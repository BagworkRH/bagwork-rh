"""Wallet ownership verification tests (Spec 04).

Ownership must be proven by a signature over the server-issued nonce; an
address alone is never sufficient, and the nonce is single-use.
"""
from django.test import TestCase
from eth_account import Account
from eth_account.messages import encode_defunct
from rest_framework import status
from rest_framework.test import APIClient

from apps.wallets.models import Wallet
from apps.wallets.services import wallet_nonce_message

from .helpers import make_user

CHAIN_ID = 11155111


def _sign(message: str, key: str) -> str:
    signed = Account.sign_message(encode_defunct(text=message), private_key=key)
    return "0x" + bytes(signed.signature).hex()


class WalletRegistrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(user=self.user)
        self.account = Account.create()

    def _register(self, address=None, chain_id=CHAIN_ID):
        return self.client.post(
            "/api/v1/me/wallets/",
            {"address": address or self.account.address, "chain_id": chain_id},
            format="json",
        )

    def test_register_returns_nonce_and_signable_message(self):
        resp = self._register()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["nonce"])
        self.assertFalse(resp.data["verified"])
        self.assertIn("verify wallet ownership", resp.data["message"])
        self.assertIn(resp.data["address"], resp.data["message"])
        self.assertIn(str(CHAIN_ID), resp.data["message"])

    def test_message_matches_service_template(self):
        resp = self._register()
        wallet = Wallet.objects.get(pk=resp.data["id"])
        self.assertEqual(resp.data["message"], wallet_nonce_message(wallet))

    def test_address_is_normalized_to_lowercase(self):
        resp = self._register(address=self.account.address.upper())
        self.assertEqual(resp.data["address"], self.account.address.lower())

    def test_register_requires_address_and_chain(self):
        resp = self.client.post("/api/v1/me/wallets/", {"address": ""}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_requires_authentication(self):
        self.client.force_authenticate(user=None)
        resp = self._register()
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_wallets(self):
        self._register()
        resp = self.client.get("/api/v1/me/wallets/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)


class WalletVerificationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(user=self.user)
        self.account = Account.create()
        registered = self.client.post(
            "/api/v1/me/wallets/",
            {"address": self.account.address, "chain_id": CHAIN_ID},
            format="json",
        )
        self.wallet_id = registered.data["id"]
        self.message = registered.data["message"]

    def _verify(self, signature):
        return self.client.post(
            f"/api/v1/me/wallets/{self.wallet_id}/verify/",
            {"signature": signature},
            format="json",
        )

    def test_valid_signature_verifies_wallet(self):
        resp = self._verify(_sign(self.message, self.account.key))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["verified"])

        wallet = Wallet.objects.get(pk=self.wallet_id)
        self.assertTrue(wallet.verified)
        self.assertEqual(wallet.nonce, "")  # nonce is single-use

    def test_wrong_signer_is_rejected(self):
        other = Account.create()
        resp = self._verify(_sign(self.message, other.key))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Wallet.objects.get(pk=self.wallet_id).verified)

    def test_signature_over_different_message_is_rejected(self):
        resp = self._verify(_sign("something else entirely", self.account.key))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Wallet.objects.get(pk=self.wallet_id).verified)

    def test_malformed_signature_returns_400(self):
        resp = self._verify("0xnot-a-signature")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replay_is_rejected_after_success(self):
        self.assertEqual(self._verify(_sign(self.message, self.account.key)).status_code, 200)
        replay = self._verify(_sign(self.message, self.account.key))
        self.assertEqual(replay.status_code, status.HTTP_409_CONFLICT)

    def test_verifying_without_pending_nonce_returns_409(self):
        Wallet.objects.filter(pk=self.wallet_id).update(nonce="")
        resp = self._verify(_sign(self.message, self.account.key))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_cannot_verify_another_sellers_wallet(self):
        other_user, _ = make_user(email="other@example.com", username="other")
        self.client.force_authenticate(user=other_user)
        resp = self._verify(_sign(self.message, self.account.key))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)