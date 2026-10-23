"use client";

import { useCallback, useState } from "react";

import ReasonPrompt from "@/components/ops/ReasonPrompt";
import { useOpsList } from "@/hooks/useOpsList";
import { listCampaigns, setCampaignStatus } from "@/services/admin";
import type { OpsCampaign } from "@/types/ops";

const STATUS_OPTIONS = [
  { label: "Active (resume or launch)", value: "ACTIVE" },
  { label: "Paused (stops new claims)", value: "PAUSED" },
  { label: "Ended", value: "ENDED" },
  { label: "Cancelled (stops new claims)", value: "CANCELLED" },
];

/**
 * Campaign directory with the emergency controls.
 *
 * Pausing or cancelling also disables claiming for that campaign's rewards —
 * enforced in `create_claim` on the server, so this console cannot leave a
 * campaign paused while its rewards stay claimable.
 */
export default function OpsCampaignsPage() {
  const list = useOpsList<OpsCampaign>(listCampaigns);
  const [target, setTarget] = useState<OpsCampaign | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = useCallback(
    async (campaign: OpsCampaign, status: string, reason: string) => {
      setBusy(true);
      setActionError(null);
      try {
        await setCampaignStatus(campaign.id, status, reason);
        setNotice(`${campaign.name} is now ${status}.`);
        setTarget(null);
        list.reload();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "The action failed.");
      } finally {
        setBusy(false);
      }
    },
    [list]
  );

  const rows = list.data?.results ?? [];

  return (
    <>
      <div className="ops-toolbar">
        <label className="field">
          <span>Status</span>
          <select
            value={String(list.filters.status ?? "")}
            onChange={(event) => list.setFilter("status", event.target.value)}
          >
            <option value="">Any</option>
            <option value="DRAFT">Draft</option>
            <option value="ACTIVE">Active</option>
            <option value="PAUSED">Paused</option>
            <option value="ENDED">Ended</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </label>
        <label className="field">
          <span>Search</span>
          <input
            type="search"
            placeholder="Campaign name or slug"
            value={String(list.filters.search ?? "")}
            onChange={(event) => list.setFilter("search", event.target.value)}
          />
        </label>
        <button className="btn btn-outline btn-sm" onClick={list.reload}>
          Refresh
        </button>
      </div>

      {notice ? <div className="banner banner-ok">{notice}</div> : null}
      {list.state === "loading" ? <p className="muted">Loading campaigns…</p> : null}
      {list.state === "error" ? <div className="banner banner-error">{list.error}</div> : null}
      {list.state === "ready" && rows.length === 0 ? (
        <p className="muted">No campaigns match this filter.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="table-cards">
          <table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Status</th>
                <th>Budget</th>
                <th>Activity</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((campaign) => (
                <tr key={campaign.id}>
                  <td data-label="Campaign">
                    <strong>{campaign.name}</strong>
                    <div className="muted">
                      {campaign.project_name} · <code>{campaign.slug}</code>
                    </div>
                    <div className="muted">
                      {new Date(campaign.start_at).toLocaleDateString()} →{" "}
                      {new Date(campaign.end_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td data-label="Status">
                    <span className={campaign.status === "ACTIVE" ? "badge badge-ok" : "badge"}>
                      {campaign.status}
                    </span>
                    <div className="muted">
                      {campaign.reward_model} · {campaign.reward_rate} {campaign.token_symbol}
                    </div>
                  </td>
                  <td data-label="Budget">
                    {campaign.budget}
                    <div className="muted">left {campaign.remaining_budget}</div>
                  </td>
                  <td data-label="Activity">
                    {campaign.participants} joined
                    <div className="muted">{campaign.rewards} rewards</div>
                  </td>
                  <td data-label="Actions">
                    <div className="ops-actions">
                      <button
                        className="btn btn-outline btn-sm"
                        onClick={() => setTarget(campaign)}
                      >
                        Change status
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="ops-pager">
        <span className="muted">
          {list.count} campaign{list.count === 1 ? "" : "s"} · showing {rows.length}
        </span>
        <div className="ops-actions">
          <button
            className="btn btn-outline btn-sm"
            disabled={!list.canPrev}
            onClick={() => list.setOffset(Math.max(0, list.offset - list.limit))}
          >
            Previous
          </button>
          <button
            className="btn btn-outline btn-sm"
            disabled={!list.canNext}
            onClick={() => list.setOffset(list.offset + list.limit)}
          >
            Next
          </button>
        </div>
      </div>

      <ReasonPrompt
        open={target !== null}
        title={`Change status — ${target?.name ?? ""}`}
        description="Pausing or cancelling also disables claiming for this campaign's rewards. Launching requires the brand to have funded the budget."
        options={STATUS_OPTIONS}
        optionsLabel="New status"
        reasonLabel="Reason"
        reasonPlaceholder="Recorded in the audit trail"
        confirmLabel="Apply"
        busy={busy}
        error={actionError}
        onCancel={() => {
          setTarget(null);
          setActionError(null);
        }}
        onConfirm={(reason, status) => {
          if (target && status) void apply(target, status, reason);
        }}
      />
    </>
  );
}
