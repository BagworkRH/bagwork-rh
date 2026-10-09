"use client";

import Link from "next/link";
import { useState } from "react";
import { formatAmount } from "@/lib/money";
import { joinCampaign } from "@/services/campaigns";
import type { Campaign } from "@/types";

export default function CampaignCard({ campaign }: { campaign: Campaign }) {
  // `campaign.joined` is the source of truth once the seller's memberships have
  // been loaded; the local flag covers the moment just after joining, before that
  // list has been re-read.
  const [joinedLocally, setJoinedLocally] = useState(false);
  const joined = campaign.joined || joinedLocally;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Joining is a server fact, not a button state.
   *
   * The participation is what the dashboard lists and what discovery matches
   * posts against, so the card only reads "Joined" once the backend has actually
   * recorded it — flipping a local flag would show a creator they were enrolled
   * when nothing was.
   */
  async function handleJoin() {
    setBusy(true);
    setError(null);
    try {
      await joinCampaign(campaign.id);
      setJoinedLocally(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join this campaign.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card campaign-card">
      <div className="campaign-card-top">
        <span className="badge badge-token">{campaign.token_symbol}</span>
        <span className={`badge ${campaign.status === "ACTIVE" ? "badge-ok" : "badge-muted"}`}>
          {campaign.status}
        </span>
      </div>
      <h3>
        <Link href={`/campaigns/${campaign.slug}`}>{campaign.name}</Link>
      </h3>
      <p className="muted">{campaign.project_name}</p>
      <p>{campaign.description}</p>

      <dl className="stats-list">
        <div>
          <dt>Budget</dt>
          <dd>
            {formatAmount(campaign.budget)} {campaign.token_symbol}
          </dd>
        </div>
        <div>
          <dt>Reward</dt>
          <dd>
            {formatAmount(campaign.reward_rate)} {campaign.token_symbol}
          </dd>
        </div>
        <div>
          <dt>Remaining</dt>
          <dd>
            {formatAmount(campaign.remaining_budget)} {campaign.token_symbol}
          </dd>
        </div>
      </dl>

      <div className="row">
        <Link href={`/campaigns/${campaign.slug}`} className="btn btn-outline btn-sm">
          Details
        </Link>
        {joined ? (
          <span className="badge badge-ok">Joined</span>
        ) : (
          <button
            className="btn btn-primary btn-sm"
            disabled={busy}
            onClick={() => void handleJoin()}
          >
            {busy ? "Joining…" : "Join campaign"}
          </button>
        )}
      </div>

      {error && <div className="banner banner-error">{error}</div>}
    </article>
  );
}