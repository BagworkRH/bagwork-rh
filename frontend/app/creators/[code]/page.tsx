import Link from "next/link";
import { notFound } from "next/navigation";

import { BarSeries } from "@/components/charts";
import { ArrowRightIcon, CoinsIcon, TargetIcon, TrophyIcon, UsersIcon } from "@/components/icons";
import { Avatar, StatTile } from "@/components/ui";
import { formatAmount } from "@/lib/money";
import { getCreatorCard } from "@/services/leaderboard";
import type { CreatorCard } from "@/types";

async function loadCard(code: string): Promise<CreatorCard | null> {
  try {
    return await getCreatorCard(code);
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: { code: string } }) {
  const card = await loadCard(params.code);
  if (!card) return { title: "Creator not found · bagworkRH" };

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

/**
 * A creator's public profile.
 *
 * The same facts as the share card, laid out as a page: what they earned, where
 * they stand, and how it moved. It obeys the board's opt-out — a creator who hid
 * their earnings keeps their rank and standing and the figures are simply
 * absent, rather than being shown as zero.
 */
export default async function CreatorProfilePage({ params }: { params: { code: string } }) {
  const card = await loadCard(params.code);
  if (!card) notFound();

  const symbol = card.best_campaign?.token_symbol ?? "";
  const standing =
    card.best_campaign?.rank && card.best_campaign.entrants
      ? `#${card.best_campaign.rank} of ${card.best_campaign.entrants}`
      : null;

  return (
    <div className="page" style={{ maxWidth: 980 }}>
      <Link href="/leaderboard" className="muted" style={{ fontSize: "0.875rem" }}>
        ← Leaderboard
      </Link>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="row-between" style={{ alignItems: "flex-start" }}>
          <div className="row" style={{ gap: 14, alignItems: "center" }}>
            <Avatar name={card.display_name} src={card.avatar_url} size="lg" />
            <div>
              <h1 style={{ marginBottom: 2 }}>{card.display_name}</h1>
              <div className="row" style={{ gap: 8 }}>
                {card.username ? <span className="muted">@{card.username}</span> : null}
                <span className="chip">{card.seller_code}</span>
                {card.demo ? <span className="demo-chip">demo</span> : null}
              </div>
            </div>
          </div>
          <div className="actions" style={{ marginTop: 0 }}>
            <Link href={`/card/${card.seller_code}`} className="btn btn-outline btn-sm">
              Share card <ArrowRightIcon size={14} />
            </Link>
          </div>
        </div>
      </div>

      <div className="stat-grid" style={{ marginTop: 16 }}>
        <StatTile
          label="Total paid"
          value={card.hidden ? "Hidden" : formatAmount(card.paid ?? "0")}
          unit={card.hidden ? undefined : symbol}
          icon={CoinsIcon}
          tone="green"
          sub={card.hidden ? "Earnings private by choice" : "Settled on-chain"}
        />
        <StatTile
          label="Verified posts paid"
          value={card.rewards.toLocaleString("en-US")}
          icon={TrophyIcon}
          tone="brand"
        />
        <StatTile
          label="Campaigns"
          value={card.campaigns.toLocaleString("en-US")}
          icon={TargetIcon}
          tone="blue"
        />
        <StatTile
          label="Best standing"
          value={standing ?? "—"}
          icon={UsersIcon}
          tone="brand"
          sub={card.best_campaign ? card.best_campaign.name : undefined}
        />
      </div>

      {card.hidden ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>Earnings are private</h2>
          <p className="muted">
            This creator chose not to publish their earnings. Their rank and standing stay
            visible; the figures do not.
          </p>
        </div>
      ) : (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="board-head">
            <div className="board-title">
              <h2>Earnings, last 30 days</h2>
              <span className="muted" style={{ fontSize: "0.82rem" }}>
                {formatAmount(card.paid ?? "0")} {symbol} settled in total
              </span>
            </div>
            <div className="board-controls">
              <span className="chip">
                7D <strong style={{ color: "var(--text)" }}>{formatAmount(card.delta_7d ?? "0")}</strong>
              </span>
              <span className="chip">
                30D <strong style={{ color: "var(--text)" }}>{formatAmount(card.delta_30d ?? "0")}</strong>
              </span>
            </div>
          </div>
          <BarSeries values={card.series} tone="green" unit={symbol} />
        </div>
      )}

      {card.best_campaign ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="board-head">
            <div className="board-title">
              <h2>Best campaign</h2>
            </div>
            <Link href={`/campaigns/${card.best_campaign.slug}`} className="btn btn-outline btn-sm">
              View campaign <ArrowRightIcon size={14} />
            </Link>
          </div>
          <dl className="stats-list" style={{ borderTop: 0, paddingTop: 0 }}>
            <div>
              <dt>Campaign</dt>
              <dd style={{ fontFamily: "var(--font-sans)" }}>{card.best_campaign.name}</dd>
            </div>
            <div>
              <dt>Standing</dt>
              <dd>{standing ?? "—"}</dd>
            </div>
            <div>
              <dt>Entrants</dt>
              <dd>{card.best_campaign.entrants}</dd>
            </div>
            <div>
              <dt>Token</dt>
              <dd>{symbol || "—"}</dd>
            </div>
          </dl>
        </div>
      ) : null}

      <p className="muted" style={{ marginTop: 16, fontSize: "0.8125rem" }}>
        Figures come from settled rewards only — payouts that may still be reversed are not
        published. Wallet addresses are never shown.
      </p>
    </div>
  );
}
