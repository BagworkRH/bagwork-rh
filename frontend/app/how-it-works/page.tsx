import Link from "next/link";

export const metadata = { title: "How It Works — CryptoRewards" };

export default function HowItWorksPage() {
  return (
    <div className="container section" style={{ maxWidth: 760 }}>
      <h1>How CryptoRewards works</h1>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>For sellers</h2>
        <ol>
          <li>
            <strong>Create an account</strong> — sign up and you&apos;ll get a
            unique, secure seller code (for example{" "}
            <code className="wallet-chip">SELLER-7K4M2P</code>).
          </li>
          <li>
            <strong>Connect X</strong> — link your X account through the official
            OAuth flow. Only the permissions we actually need are requested.
          </li>
          <li>
            <strong>Connect a wallet</strong> — link an EVM wallet and prove
            ownership by signing a nonce message. We never ask for your seed
            phrase or private key.
          </li>
          <li>
            <strong>Join a campaign</strong> — choose an active campaign that
            fits you and publish qualifying posts with the required hashtags or
            mentions.
          </li>
          <li>
            <strong>Get rewarded</strong> — once a post is verified and metrics
            are recorded, a reward is calculated and, after review, becomes
            available to claim on-chain.
          </li>
        </ol>
      </section>

      <section className="card">
        <h2>For projects</h2>
        <p className="muted">
          Set a campaign budget, reward model, eligibility rules, and caps. The
          platform verifies posts honestly, protects your budget with locks and
          reserves, and keeps an append-only audit trail of every financial
          change.
        </p>
        <Link href="/campaigns" className="btn btn-outline">
          Explore live campaigns
        </Link>
      </section>
    </div>
  );
}