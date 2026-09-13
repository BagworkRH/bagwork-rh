# 01 — Product & UI Specification

Crypto-native platform inspired by the UsePaid workflow, with **original
branding, UI, copy, and implementation** (never copy UsePaid assets/logos/text).

## Core user journey
1. Visitor lands on homepage.
2. Seller chooses **Onboard a Seller**.
3. Seller authenticates with X.
4. Seller connects an EVM wallet.
5. Platform creates a unique seller code.
6. Seller joins a campaign and publishes qualifying X posts.
7. Platform verifies and tracks qualifying posts.
8. Reward engine calculates earnings.
9. Seller views pending/available rewards.
10. Seller claims eligible rewards on-chain.

## Primary navigation
Home · Campaigns · How It Works · Dashboard · Connect Wallet · Profile · Help

## Homepage
- **Hero:** value proposition ("earn crypto rewards for verified social
  promotion"), primary CTA **Onboard a Seller**, secondary **Explore Campaigns**,
  wallet connection button in header.
- Sections: How it works · Featured campaigns · Live platform statistics ·
  Seller benefits · Project benefits · Security/trust · FAQ · Footer.

## Seller onboarding
1. **X account** — Sign in with X, request only required permissions,
   display connected username and avatar.
2. **Wallet** — Connect EVM wallet, display shortened address, never expose
   private keys/seed phrases.
3. **Seller profile** — display X username, wallet address; generate unique
   seller code with copy button and explanation.
4. **Confirmation** — X account, wallet, seller code, status, link to dashboard.

## Seller dashboard
Top cards: total earnings · available to claim · pending rewards · posts
tracked · verified posts · total engagement.
Sections: active campaigns · recent tracked posts · reward history ·
wallet activity · seller code · account status.

## Campaign page
Name, project/token, description, budget, start/end, reward rules, required
hashtags/mentions, eligibility, maximum reward, remaining budget, Join button,
rules and anti-fraud notice.

## Post detail
Post URL, date, campaign, seller, verification status, impressions/views,
likes, reposts, replies, calculated reward, last metrics update, rejection
reason.

## Reward page
Statuses: Pending · Approved · Available · Claimed · Failed · Reversed.
Show transaction hash for on-chain claims.

## Admin UI
Overview · Campaigns · Sellers · X accounts · Posts · Rewards · Claims ·
Transactions · Fraud/risk · Settings · Audit logs.

## Design direction
- Dark crypto-native interface; high contrast; clean cards and compact tables.
- Responsive from 320px mobile upward; original visual identity.
- Subtle animation only where it improves feedback.
- Wallet/X status obvious.

## Accessibility
Keyboard navigable, visible focus states, semantic HTML, accessible labels,
no communicating state through color alone.

## Error states
Every external integration needs: loading, empty, retry, permission-denied,
network failure, rate-limit, transaction pending, transaction failed.

## Security UX
Never ask for seed phrase, private key, or wallet password. Always show:
connected wallet, network, transaction confirmation, claim amount,
destination wallet.