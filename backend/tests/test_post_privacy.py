"""Tests that X-derived post data is not publicly readable.

Post URLs and engagement counts come from X's API. Exposing them to anonymous
callers is a data-protection problem, so these endpoints are staff-only and a
creator has their own scoped view. Both halves are tested: the lock, and the
replacement.
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.social.models import PostVerificationStatus, SocialPost

from .helpers import make_campaign, make_staff, make_user, make_verified_post


class PublicPostEndpointsAreLockedTests(TestCase):
    """`GET /api/v1/posts/` used to be AllowAny. It must stay that way closed."""

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="locked-campaign")
        self.post = make_verified_post(self.profile, self.campaign, external_id="lock-1")

    def test_anonymous_cannot_list_posts(self):
        self.client.force_authenticate(None)
        resp = self.client.get("/api/v1/posts/")
        self.assertIn(resp.status_code, (401, 403))

    def test_authenticated_creator_cannot_list_all_posts(self):
        # Being logged in is not enough: this shows every seller's posts.
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/posts/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_read_a_post(self):
        self.client.force_authenticate(None)
        resp = self.client.get(f"/api/v1/posts/{self.post.pk}/")
        self.assertIn(resp.status_code, (401, 403))

    def test_creator_cannot_read_another_sellers_post_by_id(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get(f"/api/v1/posts/{self.post.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_list_posts(self):
        self.client.force_authenticate(make_staff())
        resp = self.client.get("/api/v1/posts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_staff_can_read_a_post(self):
        self.client.force_authenticate(make_staff())
        resp = self.client.get(f"/api/v1/posts/{self.post.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class MyPostsEndpointTests(TestCase):
    """The creator-facing replacement must show own posts and only own posts."""

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(self.user)
        self.campaign = make_campaign(slug="my-posts-campaign")

    def test_creator_sees_their_own_post(self):
        post = make_verified_post(self.profile, self.campaign, external_id="mine-1")
        resp = self.client.get("/api/v1/me/posts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([p["id"] for p in resp.data], [post.pk])

    def test_creator_never_sees_another_sellers_post(self):
        other_user, other_profile = make_user(
            email="other@example.com", username="other"
        )
        others_post = make_verified_post(other_profile, self.campaign, external_id="theirs-1")
        resp = self.client.get("/api/v1/me/posts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn(others_post.pk, [p["id"] for p in resp.data])

    def test_creator_sees_why_a_post_was_rejected(self):
        # They cannot act on a rejection without knowing the reason.
        rejected = SocialPost.objects.create(
            seller=self.profile,
            campaign=self.campaign,
            external_post_id="rejected-1",
            post_url="https://x.com/i/status/rejected-1",
            text_snapshot="#ad",
            published_at=self.campaign.start_at,
            verification_status=PostVerificationStatus.NOT_ORIGINAL,
            rejection_reason="Post is a repost, not original content.",
            is_repost=True,
        )
        resp = self.client.get("/api/v1/me/posts/")
        row = next(p for p in resp.data if p["id"] == rejected.pk)
        self.assertEqual(row["verification_status"], PostVerificationStatus.NOT_ORIGINAL)
        self.assertIn("repost", row["rejection_reason"])

    def test_can_filter_by_status(self):
        make_verified_post(self.profile, self.campaign, external_id="v-1")
        resp = self.client.get("/api/v1/me/posts/?status=VERIFIED")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(p["verification_status"] == "VERIFIED" for p in resp.data))

    def test_anonymous_cannot_read_my_posts(self):
        self.client.force_authenticate(None)
        resp = self.client.get("/api/v1/me/posts/")
        self.assertIn(resp.status_code, (401, 403))