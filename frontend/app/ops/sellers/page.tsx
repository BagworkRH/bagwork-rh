"use client";

import { useCallback, useState } from "react";

import ReasonPrompt from "@/components/ops/ReasonPrompt";
import { useOpsList } from "@/hooks/useOpsList";
import { listSellers, setSellerStatus } from "@/services/admin";
import type { OpsSeller } from "@/types/ops";

/**
 * Seller directory.
 *
 * Suspending stops a creator participating; it never touches their financial
 * history — rewards, claims and the ledger are untouched. That distinction is
 * enforced server-side and the wording here says so, rather than implying a
 * suspension erases anything.
 */
export default function OpsSellersPage() {
  const list = useOpsList<OpsSeller>(listSellers);
  const [target, setTarget] = useState<OpsSeller | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = useCallback(
    async (seller: OpsSeller, status: string, reason: string) => {
      setBusy(true);
      setActionError(null);
      try {
        await setSellerStatus(seller.id, status, reason);
        setNotice(`${seller.seller_code} is now ${status}.`);
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
          <span>Search</span>
          <input
            type="search"
            placeholder="Seller code, name or email"
            value={String(list.filters.search ?? "")}
            onChange={(event) => list.setFilter("search", event.target.value)}
          />
        </label>
        <label className="field">
          <span>Status</span>
          <select
            value={String(list.filters.status ?? "")}
            onChange={(event) => list.setFilter("status", event.target.value)}
          >
            <option value="">Any</option>
            <option value="ACTIVE">Active</option>
            <option value="SUSPENDED">Suspended</option>
            <option value="PENDING">Pending</option>
          </select>
        </label>
        <button className="btn btn-outline btn-sm" onClick={list.reload}>
          Refresh
        </button>
      </div>

      {notice ? <div className="banner banner-ok">{notice}</div> : null}
      {list.state === "loading" ? <p className="muted">Loading sellers…</p> : null}
      {list.state === "error" ? <div className="banner banner-error">{list.error}</div> : null}

      {list.state === "ready" && rows.length === 0 ? (
        <p className="muted">No sellers match this filter.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="table-cards">
          <table>
            <thead>
              <tr>
                <th>Seller</th>
                <th>Contact</th>
                <th>Status</th>
                <th>Activity</th>
                <th>Joined</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((seller) => (
                <tr key={seller.id}>
                  <td data-label="Seller">
                    <code>{seller.seller_code}</code>
                    <div className="muted">{seller.display_name || "—"}</div>
                  </td>
                  <td data-label="Contact">
                    {seller.email}
                    <div className="muted">@{seller.username}</div>
                  </td>
                  <td data-label="Status">
                    <span className={seller.status === "ACTIVE" ? "badge badge-ok" : "badge"}>
                      {seller.status}
                    </span>
                    <div className="muted">Rep {seller.reputation_score}</div>
                  </td>
                  <td data-label="Activity">
                    {seller.posts} posts · {seller.social_accounts} social
                    <div className="muted">
                      {seller.verified_wallets}/{seller.wallets} wallets verified
                    </div>
                  </td>
                  <td data-label="Joined">
                    {new Date(seller.created_at).toLocaleDateString()}
                  </td>
                  <td data-label="Actions">
                    <div className="ops-actions">
                      {seller.status === "SUSPENDED" ? (
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => setTarget(seller)}
                        >
                          Activate
                        </button>
                      ) : (
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => setTarget(seller)}
                        >
                          Suspend
                        </button>
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
          {list.count} seller{list.count === 1 ? "" : "s"} · showing {rows.length}
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
          target?.status === "SUSPENDED"
            ? `Activate ${target?.seller_code}?`
            : `Suspend ${target?.seller_code}?`
        }
        description={
          target?.status === "SUSPENDED"
            ? "They will be able to join campaigns again. Financial history is untouched."
            : "They will be blocked from joining campaigns. Rewards, claims and the ledger are not affected — only participation."
        }
        reasonLabel="Reason"
        reasonRequired={target?.status !== "SUSPENDED"}
        reasonPlaceholder="Recorded in the audit trail"
        confirmLabel={target?.status === "SUSPENDED" ? "Activate" : "Suspend"}
        danger={target?.status !== "SUSPENDED"}
        busy={busy}
        error={actionError}
        onCancel={() => {
          setTarget(null);
          setActionError(null);
        }}
        onConfirm={(reason) => {
          if (target) {
            void apply(target, target.status === "SUSPENDED" ? "ACTIVE" : "SUSPENDED", reason);
          }
        }}
      />
    </>
  );
}
