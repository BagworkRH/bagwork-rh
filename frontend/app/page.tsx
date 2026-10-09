import Link from "next/link";
import { getPlatformStats, type PlatformStats } from "@/lib/stats";

const STEPS = [
  {
    title: "Onboard as a seller",
    body: "Sign in with X and create a unique seller code.",
  },
  {
    title: "Connect your wallet",
    body: "Link an EVM wallet and verify ownership with a signature.",
  },
  {
    title: "Join a campaign",
    body: "Pick an active campaign and publish qualifying posts.",
  },
  {
    title: "Get rewarded",
    body: "We verify posts, track metrics, and pay out token rewards.",
  },
];

const FAQ = [
  {
    q: "What is bagworkRH?",
    a: "A platform that connects sellers with crypto reward campaigns. Sellers publish qualifying posts for campaigns and earn tokens for verified performance.",
  },
  {
    q: "Do I need to pay to join?",
    a: "No. Sellers join campaigns for free. Rewards are paid from campaign budgets in the campaign token.",
  },
  {
    q: "How are rewards calculated and paid?",
    a: "The platform verifies each qualifying post and its metrics, calculates the reward server-side, then lets you claim it from a linked EVM wallet on-chain.",
  },
  {
    q: "Is my wallet safe?",
    a: "We never ask for your seed phrase or private key. Wallet ownership is verified with a signature over a nonce message and rewards are claimed by your wallet.",
  },
];

/** Compact display form for a raw token amount, e.g. "1.2M", "840". */
function formatAmount(raw: string): string {
  const value = Number(raw);
  if (!Number.isFinite(value)) return "0";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M+`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

/**
 * Live platform figures. Returns null when the backend is unreachable or
 * there is nothing to report yet — in that case the strip is hidden rather
 * than showing invented numbers.
 */
function statCells(stats: PlatformStats | null) {
  if (!stats) return null;
  const hasData =
    stats.claims_completed > 0 ||
    stats.active_sellers > 0 ||
    stats.campaigns_total > 0 ||
    stats.posts_tracked > 0;
  if (!hasData) return null;

  const cells = [
    { value: formatAmount(stats.rewards_paid_total), label: "Rewards paid", money: true },
    { value: stats.claims_completed.toLocaleString("en-US"), label: "Claims completed", money: false },
    { value: stats.active_sellers.toLocaleString("en-US"), label: "Active sellers", money: false },
    { value: stats.campaigns_live.toLocaleString("en-US"), label: "Campaigns live", money: false },
  ];
  if (stats.verification_rate !== null) {
    cells.push({
      value: `${Math.round(stats.verification_rate * 100)}%`,
      label: "Posts verified",
      money: false,
    });
  }
  return cells;
}

export default async function HomePage() {
  const stats = await getPlatformStats();
  const cells = statCells(stats);

  return (
    <>
      <section className="hero container">
        <h1>Post for a campaign. Get paid on-chain.</h1>
        <p>
          Connect your social accounts and wallet, publish qualifying posts,
          and earn verified token rewards. Every claim is EIP-712 signed and
          settled on Robinhood Chain.
        </p>
        <div className="hero-ctas">
          <Link href="/dashboard" className="btn btn-primary">
            Onboard a Seller
          </Link>
          <Link href="/campaigns" className="btn btn-outline">
            Explore Campaigns
          </Link>
        </div>
      </section>

      {cells && (
        <section className="container section">
          <div className="stat-strip">
            {cells.map((cell) => (
              <div className="stat-box" key={cell.label}>
                <div className={`num${cell.money ? " money" : ""}`}>{cell.value}</div>
                <div className="muted">{cell.label}</div>
              </div>
            ))}
          </div>
          <p className="muted stat-note">
            Live figures from the platform. Rewards are only counted once a
            claim has been settled on-chain.
          </p>
        </section>
      )}

      <section className="container section">
        <h2>How it works</h2>
        <div className="stepper">
          {STEPS.map((step) => (
            <div className="step" key={step.title}>
              <h3>{step.title}</h3>
              <p className="muted">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="container section">
        <h2>For sellers &amp; creators</h2>
        <div className="grid grid-3">
          <div className="card">
            <h3>Verified earnings</h3>
            <p className="muted">
              Every reward is calculated from tracked metrics and auditable
              snapshots — no guesswork.
            </p>
          </div>
          <div className="card">
            <h3>On-chain claims</h3>
            <p className="muted">
              Approved rewards move to your connected EVM wallet as real
              token transfers.
            </p>
          </div>
          <div className="card">
            <h3>One seller code</h3>
            <p className="muted">
              A unique, secure code links your social activity to your
              campaigns without exposing extra data.
            </p>
          </div>
        </div>
      </section>

      <section className="container section">
        <h2>For projects &amp; companies</h2>
        <div className="grid grid-3">
          <div className="card">
            <h3>Budget control</h3>
            <p className="muted">
              Campaign budgets are protected with caps, reserves, and review.
              The budget can never go negative.
            </p>
          </div>
          <div className="card">
            <h3>Fraud-conscious</h3>
            <p className="muted">
              Suspicious activity flags go to a review queue; nobody is
              removed on a weak signal.
            </p>
          </div>
          <div className="card">
            <h3>Full audit trail</h3>
            <p className="muted">
              Every reward, approval, and claim is logged in an append-only
              audit log.
            </p>
          </div>
        </div>
      </section>

      <section className="container section">
        <h2>Security &amp; trust</h2>
        <p className="muted">
          We follow official X API access, encrypt OAuth credentials at rest,
          verify wallet ownership by signature, keep financial math in fixed
          precision, and never log secrets. Smart contracts are minimal,
          reviewed, and tested on testnet before release.
        </p>
      </section>

      <section className="container section">
        <h2>Frequently asked questions</h2>
        <div className="faq">
          {FAQ.map((item) => (
            <details key={item.q}>
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}