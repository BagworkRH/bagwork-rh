"use client";

import { useCallback, useState } from "react";

import ReasonPrompt from "@/components/ops/ReasonPrompt";
import { useOpsList } from "@/hooks/useOpsList";
import { listRewards, reviewReward } from "@/services/admin";
import type { OpsReward } from "@/types/ops";

type Mode = "approve" | "available" | "reverse";

const REWARD_STATUSES = [
  "PENDING",
  "VERIFIED",
  "APPROVED",
  "AVAILABLE",
  "CLAIMED",
  "FAILED",
  "REVERSED",
];

/**
 * Reward review queue: approve (PENDING→APPROVED), release (APPROVED→AVAILABLE,
 * the step that makes money claimable) and reverse. Staged on purpose so that
 * approving is never the same action as paying.
 */
export default function OpsRewardsPage() {
  const list = useOpsList<OpsReward>(listRewards);
  const [target, setTarget] = useState<{ reward: OpsReward; mode: Mode } | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = useCallback(
    async (reward: OpsReward, mode: Mode, reason: string) => {
      setBusy(true);
      setActionError(null);
      try {
        await reviewReward(reward.id, mode, reason);
        setNotice(`Reward ${reward.id} ${mode === "available" ? "released" : mode + "d"}.`);
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
            {REWARD_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status.toLowerCase()}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Seller code</span>
          <input
            type="search"
            placeholder="SELLER-XXXXXX"
            value={String(list.filters.seller_code ?? "")}
            onChange={(event) => list.setFilter("seller_code", event.target.value)}
          />
        </label>
        <button className="btn btn-outline btn-sm" onClick={list.reload}>
          Refresh
        </button>
      </div>

      {notice ? <div className="banner banner-ok">{notice}</div> : null}
      {list.state === "loading" ? <p className="muted">Loading rewards…</p> : null}
      {list.state === "error" ? <div className="banner banner-error">{list.error}</div> : null}
      {list.state === "ready" && rows.length === 0 ? (
        <p className="muted">No rewards match this filter.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="table-cards">
          <table>
            <thead>
              <tr>
                <th>Reward</th>
                <th>Seller</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Calculation</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((reward) => (
                <tr key={reward.id}>
                  <td data-label="Reward">
                    #{reward.id}
                    <div className="muted">
                      {reward.campaign} · post {reward.post}
                    </div>
                  </td>
                  <td data-label="Seller">
                    <code>{reward.seller_code}</code>
                  </td>
                  <td data-label="Amount" className="money">
                    {reward.amount} {reward.token_symbol}
                  </td>
                  <td data-label="Status">
                    <span
                      className={
                        reward.status === "AVAILABLE" || reward.status === "APPROVED"
                          ? "badge badge-ok"
                          : "badge"
                      }
                    >
                      {reward.status}
                    </span>
                  </td>
                  <td data-label="Calculation">
                    <span className="muted">{reward.explanation}</span>
                  </td>
                  <td data-label="Actions">
                    <div className="ops-actions">
                      {reward.status === "PENDING" ? (
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => setTarget({ reward, mode: "approve" })}
                        >
                          Approve
                        </button>
                      ) : null}
                      {reward.status === "APPROVED" ? (
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => setTarget({ reward, mode: "available" })}
                        >
                          Release
                        </button>
                      ) : null}
                      {["PENDING", "APPROVED", "AVAILABLE"].includes(reward.status) ? (
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => setTarget({ reward, mode: "reverse" })}
                        >
                          Reverse
                        </button>
                      ) : null}
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
          {list.count} reward{list.count === 1 ? "" : "s"} · showing {rows.length}
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
        title={
          target?.mode === "reverse"
            ? `Reverse reward #${target?.reward.id}?`
            : target?.mode === "available"
              ? `Release reward #${target?.reward.id}?`
              : `Approve reward #${target?.reward.id}?`
        }
        description={
          target?.mode === "reverse"
            ? "Reverses the payout and frees the campaign slot. A reason is required and is recorded in the audit trail."
            : target?.mode === "available"
              ? `This makes ${target?.reward.amount} ${target?.reward.token_symbol} claimable by ${target?.reward.seller_code}.`
              : "Moves the reward to APPROVED. It is not claimable until it is released."
        }
        reasonLabel="Reason"
        reasonRequired={target?.mode === "reverse"}
        reasonPlaceholder="Recorded in the audit trail"
        confirmLabel={
          target?.mode === "reverse"
            ? "Reverse"
            : target?.mode === "available"
              ? "Release"
              : "Approve"
        }
        danger={target?.mode === "reverse"}
        busy={busy}
        error={actionError}
        onCancel={() => {
          setTarget(null);
          setActionError(null);
        }}
        onConfirm={(reason) => {
          if (target) void apply(target.reward, target.mode, reason);
        }}
      />
    </>
  );
}
