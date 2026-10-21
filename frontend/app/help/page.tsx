import Link from "next/link";

export const metadata = { title: "Help — bagworkRH" };

type Topic = {
  id: string;
  title: string;
  body: string;
  /** Where the full text lives, when this entry is only a summary. */
  href?: string;
};

const TOPICS: Topic[] = [
  {
    id: "terms",
    title: "Terms of Service",
    body: "Use of the platform is subject to the campaign rules and applicable token reward terms. Rewards are not securities and nothing on this site is financial advice. The full text is on the Terms of Service page.",
    href: "/terms",
  },
  {
    id: "privacy",
    title: "Privacy Policy",
    body: "We collect only the data needed to run campaigns: your account, linked social identity, wallet addresses, and tracked post metrics. Credentials are encrypted at rest and never logged. The full text is on the Privacy Policy page.",
    href: "/privacy",
  },
  {
    id: "disclosure",
    title: "Paid Partnership Disclosure",
    body: "Sellers must disclose paid promotion where required by the platform or applicable law. Follow each campaign's disclosure guidance before posting.",
  },
  {
    id: "report",
    title: "Report a problem",
    body: "Use the reporting contact form or email support with your seller code and the relevant post URL. We review every report.",
  },
];

export default function HelpPage() {
  return (
    <div className="container section" style={{ maxWidth: 760 }}>
      <h1>Help center</h1>
      <p className="muted">Guidance, terms, privacy, and reporting.</p>

      <div className="faq">
        {TOPICS.map((topic) => (
          <details key={topic.id} id={topic.id}>
            <summary>{topic.title}</summary>
            <p>{topic.body}</p>
            {topic.href ? (
              <p>
                <Link href={topic.href}>Read the full text</Link>
              </p>
            ) : null}
          </details>
        ))}

        <details id="reward">
          <summary>How is my reward calculated?</summary>
          <p>
            Rewards are calculated server-side from campaign rules and the
            metrics snapshots of your verified post. Caps, per-seller limits,
            campaign remaining budget, and fraud review are applied before any
            reward is approved. The full calculation explanation accompanies
            every reward.
          </p>
        </details>

        <details id="claim">
          <summary>How do I claim tokens?</summary>
          <p>
            When a reward is available, the platform issues a claim
            authorization. Your wallet submits the claim transaction; the
            contract prevents replay, and once the transaction is confirmed
            the claim is marked claimed and the hash is shown on your
            dashboard.
          </p>
        </details>
      </div>
    </div>
  );
}