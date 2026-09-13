"use client";

import Link from "next/link";
import { useState } from "react";
import type { Campaign } from "@/types";

export default function CampaignCard({ campaign }: { campaign: Campaign }) {
  const [joined, setJoined] = useState(campaign.joined);

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
            {campaign.budget} {campaign.token_symbol}
          </dd>
        </div>
        <div>
          <dt>Reward</dt>
          <dd>
            {campaign.reward_rate} {campaign.token_symbol}
          </dd>
        </div>
        <div>
          <dt>Remaining</dt>
          <dd>
            {campaign.remaining_budget} {campaign.token_symbol}
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
            onClick={() => setJoined(true)}
          >
            Join campaign
          </button>
        )}
      </div>
    </article>
  );
}