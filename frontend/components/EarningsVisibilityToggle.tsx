"use client";

import { useEffect, useState } from "react";

import { getSellerProfile, updateSellerProfile } from "@/services/seller";

/**
 * The leaderboard opt-out.
 *
 * Public by default is only a choice if the way out is easy to find and honest
 * about what changes. A bare checkbox labelled "public profile" describes
 * nothing, so this states what is shown, what stays visible when it is off, and
 * what never appears at all.
 */
export default function EarningsVisibilityToggle() {
  const [visible, setVisible] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSellerProfile()
      .then((profile) => setVisible(profile.show_earnings_publicly))
      .catch(() => setVisible(null));
  }, []);

  async function toggle(next: boolean) {
    const previous = visible;
    setBusy(true);
    setError(null);
    // Move the switch immediately: waiting on a round trip makes a toggle feel
    // broken, and the request is trivially reversible if it fails.
    setVisible(next);
    try {
      const profile = await updateSellerProfile({ show_earnings_publicly: next });
      setVisible(profile.show_earnings_publicly);
    } catch {
      setVisible(previous);
      setError("Could not save that. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>Leaderboard visibility</h3>
      <p className="muted">
        The public arena shows your handle, avatar, how many rewards you were paid and
        the settled amount. It never shows your wallet address, and never a post we
        rejected.
      </p>

      {visible === null ? (
        <p className="muted">Loading your setting…</p>
      ) : (
        <label className="switch-row">
          <input
            type="checkbox"
            checked={visible}
            disabled={busy}
            onChange={(event) => void toggle(event.target.checked)}
          />
          <span>
            <strong>{visible ? "Show my earnings" : "My earnings are hidden"}</strong>
            <span className="muted">
              {visible
                ? "Your rank and amount appear on the arena."
                : "Your rank still appears; the amount does not."}
            </span>
          </span>
        </label>
      )}

      {error && <div className="banner banner-error">{error}</div>}
    </div>
  );
}
