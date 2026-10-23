"use client";

import { useCallback, useState } from "react";

import ReasonPrompt from "@/components/ops/ReasonPrompt";
import { useOpsList } from "@/hooks/useOpsList";
import { failClaim, listClaims } from "@/services/admin";
import type { OpsClaim } from "@/types/ops";

const CLAIM_STATUSES = [
  "CREATED",
  "SIGNING",
  "SUBMITTED",
  "PENDING",
  "CONFIRMED",
  "FAILED",
  "REPLACED",
  "EXPIRED",
];

/**
 * Claim and transaction directory.
 *
 * "Mark failed" records why a claim did not complete. It deliberately does not
 * burn the reward: the creator can claim again, which is what makes a failed
 * transaction recoverable instead of a support ticket.
 */
export default function OpsClaimsPage() {
  const list = useOpsList<OpsClaim>(listClaims);
  const [target, setTarget] = useState<OpsClaim | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = useCallback(
    async (claim: OpsClaim, reason: string) => {
      setBusy(true);
      setActionError(null);
      try {
        await failClaim(claim.id, reason);
        setNotice(`Claim ${claim.id} marked failed. The reward stays claimable.`);
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
            {CLAIM_STATUSES.map((status) => (
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
        <label className="field">
          <span>Transaction hash</span>
          <input
            type="search"
            placeholder="0x…"
            value={String(list.filters.transaction_hash ?? "")}
            onChange={(event) => list.setFilter("transaction_hash", event.target.value)}
          />
        </label>
        <button className="btn btn-outline btn-sm" onClick={list.reload}>
          Refresh
        </button>
      </div>

      {notice ? <div className="banner banner-ok">{notice}</div> : null}
      {list.state === "loading" ? <p className="muted">Loading claims…</p> : null}
      {list.state === "error" ? <div className="banner banner-error">{list.error}</div> : null}
      {list.state === "ready" && rows.length === 0 ? (
        <p className="muted">No claims match this filter.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="table-cards">
          <table>
            <thead>
              <tr>
                <th>Claim</th>
                <th>Seller</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((claim) => (
                <tr key={claim.id}>
                  <td data-label="Claim">
                    #{claim.id} · reward {claim.reward}
                    <div className="muted">{new Date(claim.created_at).toLocaleString()}</div>
                  </td>
                  <td data-label="Seller">
                    <code>{claim.seller_code}</code>
                    <div className="muted" style={{ overflowWrap: "anywhere" }}>
                      {claim.wallet}
                    </div>
                  </td>
                  <td data-label="Amount" className="money">
                    {claim.amount} {claim.token_symbol}
                  </td>
                  <td data-label="Status">
                    <span className={claim.status === "CONFIRMED" ? "badge badge-ok" : "badge"}>
                      {claim.status}
                    </span>
                    {claim.transaction_hash ? (
                      <div className="muted" style={{ overflowWrap: "anywhere" }}>
                        {claim.transaction_hash}
                      </div>
                    ) : null}
                    {claim.failure_reason ? (
                      <div className="muted">why: {claim.failure_reason}</div>
                    ) : null}
                  </td>
                  <td data-label="Actions">
                    <div className="ops-actions">
                      {["CREATED", "SIGNING", "SUBMITTED", "PENDING"].includes(claim.status) ? (
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => setTarget(claim)}
                        >
                          Mark failed
                        </button>
                      ) : (
                        <span className="muted">—</span>
                      )}
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
          {list.count} claim{list.count === 1 ? "" : "s"} · showing {rows.length}
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
        title={`Mark claim #${target?.id ?? ""} failed?`}
        description="Records the failure against the claim. The reward is not burned — the creator can claim again."
        reasonLabel="Reason"
        reasonRequired
        reasonPlaceholder="e.g. transaction reverted, nonce reused, RPC timeout"
        confirmLabel="Mark failed"
        danger
        busy={busy}
        error={actionError}
        onCancel={() => {
          setTarget(null);
          setActionError(null);
        }}
        onConfirm={(reason) => {
          if (target) void apply(target, reason);
        }}
      />
    </>
  );
}
