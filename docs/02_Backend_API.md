# 02 — Backend, Database & API Specification

## Stack
Python · Django · Django REST Framework · PostgreSQL · Redis · Celery ·
Gunicorn · Nginx

## Architecture
Frontend ↔ Django REST API. Django handles auth, business rules, campaigns,
sellers, reward calculations, orchestration. Celery for async jobs.
PostgreSQL is the source of truth. Redis for caching, queues, rate limiting,
Celery broker.

## Core models
`User`, `SellerProfile`, `XAccount`, `Wallet`, `Campaign`,
`CampaignParticipation`, `SocialPost`, `PostMetricSnapshot`, `Reward`,
`Claim`, `AuditLog` — full field lists in Spec 02.

Key points:
- `SocialPost.external_post_id` unique.
- Financial amounts are `Decimal`; blockchain uses integer smallest units.
- `AuditLog` append-only for sensitive actions.

## API principles
- Version APIs: `/api/v1/`.
- Serializers for validation; service classes for business logic.
- Permissions for every protected action.
- Transactions for financial state changes.
- Never trust reward amounts supplied by the client.
- Idempotency for claims and payments.

## Key endpoints
`/api/v1/auth/register|login|logout/`, `/api/v1/me/`, `/me/seller/`,
`/me/wallets/`, `/me/rewards/`, `/me/claims/`; `/api/v1/x/connect|callback|disconnect/`;
`/api/v1/campaigns/`, `/campaigns/{slug}/`, `/campaigns/{id}/join/`;
`/api/v1/posts/`, `/posts/{id}/`, `/posts/submit/`;
`/api/v1/rewards/`, `/rewards/{id}/`; `/api/v1/claims/`, `/claims/{id}/`.

## Reward calculation
Server determines reward from campaign rules, verified post status, eligible
metrics, caps, remaining budget, seller limits, fraud/risk status.
Example: `reward = eligible_impressions / 1000 * campaign_rate`, then apply
per-post cap, per-seller cap, campaign remaining budget, duplicate prevention,
invalid/fraudulent activity exclusions.

## Money precision
- No floats in financial math.
- `Decimal` for off-chain accounting.
- Integer smallest token units for on-chain.
- Token decimals defined explicitly.

## Concurrency
DB transactions + row locks for: budget deductions, reward approval, claim
creation, claim processing.

## Security
Encrypt OAuth credentials at rest · secrets via env/secret manager · HTTPS ·
validate external IDs · rate limiting · CSRF · secure cookies · never log
OAuth secrets/private keys/signing data.

## Testing
Unit + integration tests for seller-code generation, campaign eligibility,
duplicate posts, reward calculations, caps, budget exhaustion, claim
idempotency, permission boundaries, API authentication.