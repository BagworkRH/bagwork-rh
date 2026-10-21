import Link from "next/link";

export const metadata = {
  title: "Privacy Policy — bagworkRH",
  description:
    "What bagworkRH collects, why, how long it is kept, and how to have it erased. Read-only access to X, encrypted credentials, no selling of data.",
};

// Same three deployment facts as the Terms page. Keep them in step.
const LEGAL_ENTITY = "[LEGAL ENTITY NAME]";
const CONTACT_EMAIL = "[CONTACT EMAIL]";

export default function PrivacyPage() {
  return (
    <div className="container section" style={{ maxWidth: 760 }}>
      <h1>Privacy Policy</h1>
      <p className="muted">
        Last updated: 20 October 2026. This explains what {LEGAL_ENTITY}{" "}
        (&ldquo;we&rdquo;) collects when you use bagworkRH, why we need it, how
        long we keep it, and how to have it removed.
      </p>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>1. What we collect</h2>
        <ul>
          <li>
            <strong>Your account</strong> — email address, username, and a
            password we store only as a one-way hash.
          </li>
          <li>
            <strong>Your seller code</strong> — the public handle that identifies
            you in campaign records (for example{" "}
            <code className="wallet-chip">SELLER-7K4M2P</code>).
          </li>
          <li>
            <strong>Your wallet address</strong> and the signature that proves
            you control it. We never receive your private key or seed phrase.
          </li>
          <li>
            <strong>Your connected social identity</strong> — the platform
            account ID, username, display name and avatar URL returned by the
            platform&apos;s own API.
          </li>
          <li>
            <strong>Access credentials for that account</strong> — stored
            encrypted, and revocable by you at any time by disconnecting.
          </li>
          <li>
            <strong>Your posts that we track</strong> — post ID, URL, a text
            snapshot, publication date, and engagement counts, together with the
            periodic snapshots used to reproduce a reward calculation.
          </li>
          <li>
            <strong>Verification records</strong> — whether a post is your own
            original work, the evidence behind that finding, and the reason if
            it was rejected.
          </li>
          <li>
            <strong>Reward and claim records</strong> — amounts, statuses,
            timestamps and transaction hashes.
          </li>
          <li>
            <strong>Technical data</strong> — your IP address (used to apply rate
            limits and to blunt abuse), request identifiers in our logs, and
            error reports if error tracking is enabled.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>2. What we do not do</h2>
        <ul>
          <li>We do not sell, license or share your data with advertisers.</li>
          <li>
            We do not build advertising profiles, and we do not resolve your
            identity across platforms.
          </li>
          <li>
            We do not use your data to train models, and we do not make automated
            decisions about you as a person. Fraud signals queue a case for a
            human to review; the platform does not accuse anyone automatically.
          </li>
          <li>
            We do not post, reply, like, repost, follow or message on your
            behalf. Our access is read-only, and there is no code path that
            writes to your account.
          </li>
          <li>
            We never ask for your private key or seed phrase, and no legitimate
            member of our team ever will.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>3. Why we use it</h2>
        <ul>
          <li>
            <strong>To run the service you asked for</strong> — verifying that a
            post is yours, calculating and recording the reward, and settling
            your claim on-chain.
          </li>
          <li>
            <strong>To keep the platform and the money safe</strong> — rate
            limits, anti-farming signals, budget and cap enforcement, and an
            audit trail that a payout dispute can be settled against.
          </li>
          <li>
            <strong>To meet our own obligations</strong> — keeping financial
            records, and honouring the platform rules the campaigns are run
            under.
          </li>
        </ul>
        <p className="muted">
          The verification logic reads one thing from your social account: the
          platform&apos;s record of whether a post is an original, a repost or a
          quote. That single fact decides whether a payout is owed, which is why
          we ask for it and nothing more.
        </p>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>4. Who we share it with</h2>
        <ul>
          <li>
            <strong>The social platform</strong> you connect, through its
            official API — read-only, using your own authorisation.
          </li>
          <li>
            <strong>The blockchain</strong> — reward and claim amounts, the
            receiving wallet address, and transaction data are public and
            permanent by design. Nothing else about you is written on-chain.
          </li>
          <li>
            <strong>Our infrastructure providers</strong> — hosting, database
            and error monitoring, which process data only on our instructions.
          </li>
        </ul>
        <p className="muted">
          We do not sell your data. We disclose it to authorities only where the
          law requires it.
        </p>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>5. How long we keep it</h2>
        <ul>
          <li>
            <strong>Post content and metrics:</strong> erased{" "}
            <strong>365 days after the campaign it belongs to ends</strong>. The
            countdown starts at the campaign&apos;s end date rather than at the
            moment we found the post, so it measures how long the data stayed
            useful. Erasure is automatic and runs daily; the post&apos;s text,
            URL, external ID and engagement counters are removed, and the
            platform payloads we stored are deleted.
          </li>
          <li>
            <strong>Rewards and claims are kept</strong>, with their amounts and
            statuses, because they are the record a payout dispute is settled
            against and the ledger they belong to cannot be unpicked. Every
            erasure records explicitly that financial records were retained, so
            the omission is visible rather than silent.
          </li>
          <li>
            <strong>Logs and error reports</strong> are kept only as long as
            they are needed to run and secure the service.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>6. Your choices and rights</h2>
        <p>
          Two different things, and the difference matters:
        </p>
        <ul>
          <li>
            <strong>Disconnect</strong> — stops us reading your account and
            keeps your history. Nothing is deleted, because you may reconnect.
          </li>
          <li>
            <strong>Erase</strong> — available from your account settings, or
            via <code>POST /api/v1/me/data-deletion/</code> with{" "}
            <code>{'{"confirm": "DELETE"}'}</code>. This removes your
            identifiers and everything derived from the platform: post content
            is anonymised, stored credentials are destroyed and the access token
            is revoked with the platform, linked handles are replaced and the
            accounts disconnected, and your email, username and names are
            replaced with your password made unusable. It is irreversible.
          </li>
        </ul>
        <p className="muted">
          Because of the financial records described above, erasure does not
          delete your reward and claim history, and the anonymised account row
          those records point at stays. You can also ask us for a copy of your
          data, or ask us to correct it. Write to {CONTACT_EMAIL} and we will
          respond within the time the law allows; you may also complain to the
          data protection authority in your country.
        </p>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>7. Security</h2>
        <ul>
          <li>
            Access credentials for your social account are encrypted at rest,
            and can be re-encrypted under a new key without you reconnecting.
          </li>
          <li>
            Traffic is encrypted in transit, and stored credentials are never
            written to our logs.
          </li>
          <li>
            Post content is not exposed publicly: the endpoints that reveal post
            URLs or engagement counts are restricted to staff, and your own
            posts are visible only to you.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>8. Cookies and local storage</h2>
        <p className="muted">
          We do not use advertising or analytics cookies, and we do not embed
          third-party trackers. Your sign-in token is kept in your browser&apos;s
          local storage so you stay logged in; clearing your browser data or
          signing out removes it.
        </p>
      </section>

      <section className="card">
        <h2>9. Age, changes, and contact</h2>
        <ul>
          <li>bagworkRH is not for anyone under 18.</li>
          <li>
            If we change this policy we will update the date at the top, and
            material changes will be announced in the app.
          </li>
          <li>
            Questions or requests: {CONTACT_EMAIL}. See also our{" "}
            <Link href="/terms">Terms of Service</Link>.
          </li>
        </ul>
      </section>
    </div>
  );
}
