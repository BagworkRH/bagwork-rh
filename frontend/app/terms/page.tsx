import Link from "next/link";

export const metadata = {
  title: "Terms of Service — bagworkRH",
  description:
    "The rules for using bagworkRH: campaigns, verified original posts, fixed rewards, on-chain claims, and what happens when a post does not qualify.",
};

// These three values are the only deployment-specific facts in this document.
// Fill them in before launch: X's developer settings require this page to be
// live and to name the operating entity, so an unfilled value here is a
// compliance problem rather than a cosmetic one.
const LEGAL_ENTITY = "[LEGAL ENTITY NAME]";
const CONTACT_EMAIL = "[CONTACT EMAIL]";
const GOVERNING_LAW = "[JURISDICTION]";

export default function TermsPage() {
  return (
    <div className="container section" style={{ maxWidth: 760 }}>
      <h1>Terms of Service</h1>
      <p className="muted">
        Last updated: 20 October 2026. These terms are between you and{" "}
        {LEGAL_ENTITY} (&ldquo;we&rdquo;, &ldquo;us&rdquo;), which operates
        bagworkRH. By creating an account or claiming a reward you accept them.
      </p>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>1. Who can use bagworkRH</h2>
        <ul>
          <li>You must be 18 or older and able to enter a contract.</li>
          <li>
            One account per person. Accounts are not transferable, and a seller
            code identifies one person.
          </li>
          <li>
            You are responsible for what happens through your account and for
            keeping your password safe.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>2. Campaigns and rewards</h2>
        <p>
          A brand funds a campaign and sets a <strong>fixed reward</strong> per
          qualifying post. The campaign&apos;s budget, reward rate and maximum
          post count are fixed when it is created and cannot be changed
          afterwards — changing them mid-flight would make calculated rewards
          impossible to reproduce.
        </p>
        <ul>
          <li>
            Rewards are calculated server-side from the campaign rules and the
            recorded metrics of your verified post, then applied against the
            campaign&apos;s caps and remaining budget.
          </li>
          <li>
            A campaign may limit how many rewards one seller can earn. Caps are
            enforced at payout, not just at sign-up.
          </li>
          <li>
            Money is only promised when the budget to pay it exists. A reward
            can be <strong>reversed</strong> if it was paid in error or if the
            post is later found not to qualify; a reversal releases the campaign
            slot and is recorded in the audit trail.
          </li>
          <li>
            Rewards are not securities and nothing on this site is financial,
            investment or tax advice.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>3. What qualifies as a post</h2>
        <p>
          You are paid for producing something, not for amplifying someone
          else. A post must be <strong>your own original content</strong>.
        </p>
        <ul>
          <li>
            Reposts and quotes of another account&apos;s post do not qualify,
            even if you add a comment. We determine this from the
            platform&apos;s own record of the post&apos;s relationship to other
            posts.
          </li>
          <li>
            The post must satisfy the campaign&apos;s requirements — required
            hashtags or mentions, and the campaign window.
          </li>
          <li>
            If a campaign is a paid promotion, you must disclose it as the
            platform and applicable law require.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>4. Verification, and what happens if a post is rejected</h2>
        <p>
          We read your post and the platform&apos;s data about it to answer one
          question: is this your own original work? We use{" "}
          <strong>read-only</strong> access. We never post, reply, like, repost,
          follow or message on your behalf, and there is no code path that
          writes to your account on X.
        </p>
        <ul>
          <li>
            If we cannot confirm a fact — for example the platform is
            unavailable — the post is <strong>not</strong> treated as
            qualifying. We fail closed rather than paying on an assumption.
          </li>
          <li>
            Rejection reasons are shown to you on your dashboard so you can act
            on them.
          </li>
          <li>
            If you believe a decision is wrong, contact us at {CONTACT_EMAIL}{" "}
            with your seller code and the post URL. Every report is reviewed by
            a person.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>5. Claiming tokens</h2>
        <ul>
          <li>
            When a reward becomes claimable we issue a signed authorisation for
            your wallet. <strong>You</strong> submit the claim transaction and
            pay the network fee; we never hold your keys or move funds from your
            wallet.
          </li>
          <li>
            Claim authorisations are bound to the chain, the contract and an
            expiry, so they cannot be replayed.
          </li>
          <li>
            On-chain transactions are irreversible. A 15% platform fee is
            charged to the brand on top of your reward — it is not deducted from
            your amount.
          </li>
          <li>
            Cryptocurrency values fluctuate and transfers carry risk. We do not
            guarantee any fiat value for a reward.
          </li>
        </ul>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>6. Conduct that will get an account suspended</h2>
        <ul>
          <li>
            Post farming, coordinated posting across accounts, or using multiple
            accounts to exceed a campaign&apos;s limits.
          </li>
          <li>
            Automated submission, scraping, or any attempt to bypass rate
            limits.
          </li>
          <li>
            Inflating metrics, faking originality, or submitting posts that are
            not yours.
          </li>
          <li>
            Sharing one wallet across several seller accounts, or attempting to
            claim rewards that are not yours.
          </li>
        </ul>
        <p className="muted">
          We bound losses per account and queue cross-account evidence for human
          review. Where an account is suspended, rewards already promised remain
          subject to the audit trail and may be reversed.
        </p>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <h2>7. Availability, changes, and liability</h2>
        <ul>
          <li>
            The service is provided as-is. We may change, pause or withdraw
            features, and we may amend these terms — material changes will be
            announced on this page with a new date.
          </li>
          <li>
            To the extent the law allows, we are not liable for lost profits,
            lost rewards, or losses caused by third-party platforms, networks or
            wallets.
          </li>
          <li>
            Nothing here limits liability that cannot lawfully be limited, and
            nothing affects your statutory rights.
          </li>
          <li>These terms are governed by the laws of {GOVERNING_LAW}.</li>
        </ul>
      </section>

      <section className="card">
        <h2>8. Your data and how to contact us</h2>
        <p className="muted">
          What we collect, why, how long we keep it, and how to have it erased is
          set out in the <Link href="/privacy">Privacy Policy</Link>. Questions
          about these terms: {CONTACT_EMAIL}.
        </p>
      </section>
    </div>
  );
}
