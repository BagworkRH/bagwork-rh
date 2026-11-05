import { notFound } from "next/navigation";

import DeltaChip from "@/components/DeltaChip";
import ShareCardButton from "@/components/ShareCardButton";
import Sparkline from "@/components/Sparkline";
import { formatAmount } from "@/lib/money";
import type { CreatorCard } from "@/types";

import { apiBaseUrl } from "@/lib/api";

/**
 * A creator's public earnings card.
 *
 * A server component on purpose: the Open Graph tags are the point. A link that
 * unfurls with "Isaac earned 2 USDG on bagworkRH" travels on its own, while a
 * bare URL gets ignored - so the metadata is the feature, and the page is just
 * what you see once you click it.
 *
 * Revalidated rather than live: a shared card does not need to be current to the
 * second, and caching keeps a viral link from hammering the API.
 */
export const revalidate = 60;

async function loadCard(code: string): Promise<CreatorCard | null> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/card/${code}/`, { next: { revalidate: 60 } });
  if (response.status === 404) return null;
  if (!response.ok) return null;
  return (await response.json()) as CreatorCard;
}

export async function generateMetadata({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const card = await loadCard(code);

  if (!card) {
    return { title: "Card not found · bagworkRH" };
  }
  const title = card.hidden
    ? `${card.display_name} on bagworkRH`
    : `${card.display_name} earned ${formatAmount(card.paid ?? "0")} ${
        card.best_campaign?.token_symbol ?? ""
      } on bagworkRH`.trim();

  return {
    title,
    description: card.hidden
      ? "A creator on bagworkRH. Their earnings are private."
      : `Paid for ${card.rewards} verified ${card.rewards === 1 ? "post" : "posts"}. Every figure is money that actually moved.`,
    openGraph: { title, type: "profile" },
    twitter: { card: "summary_large_image", title },
  };
}

export default async function CardPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const card = await loadCard(code);
  if (!card) notFound();

  const symbol = card.best_campaign?.token_symbol ?? "";
  const standing =
    card.best_campaign?.rank && card.best_campaign.entrants
      ? `#${card.best_campaign.rank} of ${card.best_campaign.entrants} in ${card.best_campaign.name}`
      : card.campaigns > 0
        ? `earning in ${card.campaigns} ${card.campaigns === 1 ? "campaign" : "campaigns"}`
        : "not paid yet";

  return (
    <div className="container section">
      <article className="earn-card">
        <header className="earn-card-head">
          {card.avatar_url ? (
            /* eslint-disable-next-line @next/next/no-img-element -- remote avatar; the
               optimizer needs sharp, which this image deliberately does not ship */
            <img className="earn-avatar" src={card.avatar_url} alt="" width={56} height={56} />
          ) : (
            <span className="earn-avatar earn-initials" aria-hidden="true">
              {card.display_name.slice(0, 2).toUpperCase()}
            </span>
          )}
          <div>
            <h1>{card.display_name}</h1>
            <p className="muted">{card.username ? `@${card.username}` : card.seller_code}</p>
          </div>
        </header>

        {card.hidden ? (
          <p className="earn-figure muted">Earnings hidden</p>
        ) : (
          <p className="earn-figure">
            {formatAmount(card.paid ?? "0")} <small>{symbol}</small>
          </p>
        )}

        <p className="muted">{standing}</p>
        {card.demo && (
          <p className="muted">Demonstration data, not a real payout.</p>
        )}

        {!card.hidden && (
          <>
            <Sparkline values={card.series} tone="up" height={44} />
            <div className="earn-deltas">
              <span className="muted">7d</span> <DeltaChip value={card.delta_7d} symbol={symbol} />
              <span className="muted">30d</span> <DeltaChip value={card.delta_30d} symbol={symbol} />
            </div>
          </>
        )}

        <footer className="earn-card-foot">
          <span className="muted">
            {card.hidden
              ? "Earnings private by choice."
              : `${card.rewards} verified ${card.rewards === 1 ? "post" : "posts"} paid.`}
          </span>
          <ShareCardButton title={`${card.display_name} on bagworkRH`} />
        </footer>
      </article>
    </div>
  );
}
