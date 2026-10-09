"use client";

import { useEffect, useState } from "react";
import CampaignCard from "@/components/CampaignCard";
import { getMyCampaigns } from "@/services/campaigns";
import type { Campaign } from "@/types";

/**
 * The campaign grid, with the seller's own memberships layered on.
 *
 * The list comes from the public endpoint, which cannot know who is asking, so
 * `joined` on those payloads is always false. This fills it in from
 * `/me/campaigns/` once, on the client, where the token actually lives —
 * otherwise a seller sees "Join campaign" for campaigns they are already in.
 */
export default function CampaignGrid({ campaigns }: { campaigns: Campaign[] }) {
  const [joinedIds, setJoinedIds] = useState<number[]>([]);

  useEffect(() => {
    let cancelled = false;
    getMyCampaigns()
      .then((mine) => {
        if (!cancelled) setJoinedIds(mine.map((c) => c.campaign_id));
      })
      .catch(() => {
        // Signed out, or the call failed: the public view is still correct, it
        // just cannot say which campaigns are already joined.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="grid">
      {campaigns.map((campaign) => (
        <CampaignCard
          key={campaign.id}
          campaign={{ ...campaign, joined: joinedIds.includes(campaign.id) }}
        />
      ))}
    </div>
  );
}
