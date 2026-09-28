import Link from "next/link";

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

export default function HomePage() {
  return (
    <>
      <section className="hero container">
        <h1>Post for a campaign. Get paid on-chain.</h1>
        <p>
          Connect your X account and wallet, publish qualifying posts, and
          earn verified token rewards. Every claim is EIP-712 signed and settled
          on Robinhood Chain.
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

      <section className="container section">
        <div className="stat-strip">
          <div className="stat-box">
            <div className="num money">$1.2M+</div>
            <div className="muted">Rewards paid</div>
          </div>
          <div className="stat-box">
            <div className="num">8.4k</div>
            <div className="muted">Active sellers</div>
          </div>
          <div className="stat-box">
            <div className="num">240+</div>
            <div className="muted">Campaigns live</div>
          </div>
          <div className="stat-box">
            <div className="num">99.9%</div>
            <div className="muted">Verification rate</div>
          </div>
        </div>
      </section>

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
              A unique, secure code links your X activity to your campaigns
              without exposing extra data.
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