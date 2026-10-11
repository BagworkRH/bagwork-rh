"use client";

import { useEffect, useState } from "react";
import { getMyCampaigns, joinCampaign } from "@/services/campaigns";

/**
 * Join a campaign from its detail page.
 *
 * Client-side on purpose: joining needs the bearer token, which only exists in
 * the browser. The page around this is server-rendered from the public endpoint,
 * so the `joined` flag it could pass down is always false — this resolves the
 * real membership from `/me/campaigns/` and reports it honestly.
 */
export default function JoinCampaignButton({
  campaignId,
  initiallyJoined = false,
}: {
  campaignId: number;
  initiallyJoined?: boolean;
}) {
  const [joined, setJoined] = useState(initiallyJoined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMyCampaigns()
      .then((mine) => {
        if (!cancelled) setJoined(mine.some((c) => c.campaign_id === campaignId));
      })
      .catch(() => {
        // Signed out, or the call failed: offering "Join campaign" is then the
        // honest state, and the attempt will explain itself if it is rejected.
      });
    return () => {
      cancelled = true;
    };
  }, [campaignId]);

  async function handleJoin() {
    setBusy(true);
    setError(null);
    try {
      await joinCampaign(campaignId);
      setJoined(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join this campaign.");
    } finally {
      setBusy(false);
    }
  }

  if (joined) {
    return <span className="badge badge-ok">Joined</span>;
  }

  return (
    <>
      <button
        className="btn btn-primary"
        disabled={busy}
        onClick={() => void handleJoin()}
      >
        {busy ? "Joining…" : "Join campaign"}
      </button>
      {error && <div className="banner banner-error">{error}</div>}
    </>
  );
}
