"use client";

import Link from "next/link";
import { useState } from "react";

import { ArrowRightIcon, ClockIcon, TargetIcon } from "@/components/icons";
import { ProgressBar } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { formatAmount } from "@/lib/money";
import { joinCampaign } from "@/services/campaigns";
import type { Campaign } from "@/types";

function daysLeft(endAt: string): number | null {
  const end = new Date(endAt).getTime();
  if (!Number.isFinite(end)) return null;
  return Math.ceil((end - Date.now()) / 86_400_000);
}

function statusBadge(status: Campaign["status"]) {
  if (status === "ACTIVE") return "badge badge-ok";
  if (status === "PAUSED") return "badge badge-warn";
  if (status === "DRAFT") return "badge badge-muted";
  return "badge badge-muted";
}

export default function CampaignCard({ campaign }: { campaign: Campaign }) {
  // `campaign.joined` is the source of truth once the seller's memberships have
  // been loaded; the local flag covers the moment just after joining, before
  // that list has been re-read.
  const [joinedLocally, setJoinedLocally] = useState(false);
  const joined = campaign.joined || joinedLocally;
  const [busy, setBusy] = useState(false);
  const { success, error: toastError } = useToast();

  const budget = Number(campaign.budget);
  const remaining = Number(campaign.remaining_budget);
  const spent = Number.isFinite(budget) && Number.isFinite(remaining) ? Math.max(0, budget - remaining) : 0;
  const usedPct = budget > 0 ? (spent / budget) * 100 : 0;
  const capacity = Number(campaign.reward_rate) > 0 ? Math.floor(budget / Number(campaign.reward_rate)) : 0;
  const paidPayouts = Number(campaign.reward_rate) > 0 ? Math.floor(spent / Number(campaign.reward_rate)) : 0;
  const left = daysLeft(campaign.end_at);

  /**
   * Joining is a server fact, not a button state. The participation is what the
   * dashboard lists and what discovery matches posts against, so the card only
   * reads "Joined" once the backend has recorded it.
   */
  async function handleJoin() {
    setBusy(true);
    try {
      await joinCampaign(campaign.id);
      setJoinedLocally(true);
      success("You joined the campaign", "Publish an original post that meets its requirements to earn.");
    } catch (err) {
      toastError("Could not join this campaign", err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card campaign-card card-interactive">
      <div className="campaign-card-top">
        <span className="badge badge-token badge-plain">{campaign.token_symbol}</span>
        <span className={statusBadge(campaign.status)}>{campaign.status}</span>
      </div>

      <h3>
        <Link href={`/campaigns/${campaign.slug}`}>{campaign.name}</Link>
      </h3>
      <p className="campaign-brand">
        <TargetIcon size={14} /> {campaign.project_name}
      </p>
      <p className="campaign-desc">{campaign.description}</p>

      <dl className="campaign-metrics">
        <div>
          <dt>Reward / post</dt>
          <dd>
            {formatAmount(campaign.reward_rate)} {campaign.token_symbol}
          </dd>
        </div>
        <div>
          <dt>Budget</dt>
          <dd>
            {formatAmount(campaign.budget)} {campaign.token_symbol}
          </dd>
        </div>
        <div>
          <dt>Remaining</dt>
          <dd>
            {formatAmount(campaign.remaining_budget)} {campaign.token_symbol}
          </dd>
        </div>
      </dl>

      <ProgressBar value={usedPct} tone={usedPct >= 90 ? "warn" : "brand"} label="Budget used" />
      <div className="campaign-progress-meta">
        <span>
          {paidPayouts} of {capacity} payouts settled
        </span>
        <span className="row" style={{ gap: 4 }}>
          <ClockIcon size={13} />
          {left === null ? "No end date" : left > 0 ? `${left} day${left === 1 ? "" : "s"} left` : "Ended"}
        </span>
      </div>

      <div className="actions">
        <Link href={`/campaigns/${campaign.slug}`} className="btn btn-outline btn-sm">
          Details
        </Link>
        {joined ? (
          <span className="badge badge-ok">Joined</span>
        ) : (
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void handleJoin()}>
            {busy ? "Joining…" : (
              <>
                Join campaign <ArrowRightIcon size={14} />
              </>
            )}
          </button>
        )}
      </div>
    </article>
  );
}
