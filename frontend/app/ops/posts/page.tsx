"use client";

import { useCallback, useState } from "react";

import ReasonPrompt from "@/components/ops/ReasonPrompt";
import { useOpsList } from "@/hooks/useOpsList";
import { REJECTION_STATUSES, listPosts, reviewPost } from "@/services/admin";
import type { OpsPost } from "@/types/ops";

const STATUS_FILTERS = [
  "DISCOVERED",
  "METRICS_PENDING",
  "VERIFIED",
  "REWARD_CALCULATED",
  "APPROVED",
  "NOT_ELIGIBLE",
  "DUPLICATE",
  "OUTSIDE_CAMPAIGN_WINDOW",
  "REQUIREMENT_MISSING",
  "NOT_ORIGINAL",
  "PROVIDER_ERROR",
  "SUSPICIOUS_ACTIVITY",
];

const REJECTION_OPTIONS = REJECTION_STATUSES.map((value) => ({
  label: value.replace(/_/g, " ").toLowerCase(),
  value,
}));

/**
 * Post review queue. Approving marks a post VERIFIED but pays nothing — the
 * reward engine calculates separately, so money cannot move from this screen.
 */
export default function OpsPostsPage() {
  const list = useOpsList<OpsPost>(listPosts);
  const [target, setTarget] = useState<{ post: OpsPost; mode: "approve" | "reject" } | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = useCallback(
    async (post: OpsPost, mode: "approve" | "reject", reason: string, rejection: string) => {
      setBusy(true);
      setActionError(null);
      try {
        await reviewPost(post.id, mode, reason, mode === "reject" ? rejection : "");
        setNotice(`Post ${post.external_post_id.slice(-8)} ${mode}d.`);
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
          <span>Verification status</span>
          <select
            value={String(list.filters.status ?? "")}
            onChange={(event) => list.setFilter("status", event.target.value)}
          >
            <option value="">Any</option>
            {STATUS_FILTERS.map((status) => (
              <option key={status} value={status}>
                {status.replace(/_/g, " ").toLowerCase()}
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
      {list.state === "loading" ? <p className="muted">Loading posts…</p> : null}
      {list.state === "error" ? <div className="banner banner-error">{list.error}</div> : null}
      {list.state === "ready" && rows.length === 0 ? (
        <p className="muted">No posts match this filter.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="table-cards">
          <table>
            <thead>
              <tr>
                <th>Post</th>
                <th>Seller</th>
                <th>Status</th>
                <th>Why</th>
                <th>Engagement</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((post) => (
                <tr key={post.id}>
                  <td data-label="Post">
                    <a href={post.post_url} target="_blank" rel="noopener noreferrer">
                      {post.external_post_id.slice(-8)}
                    </a>
                    <div className="muted">
                      {post.campaign ?? "no campaign"} ·{" "}
                      {new Date(post.published_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td data-label="Seller">
                    <code>{post.seller_code}</code>
                  </td>
                  <td data-label="Status">
                    <span
                      className={
                        post.verification_status === "VERIFIED" ? "badge badge-ok" : "badge"
                      }
                    >
                      {post.verification_status}
                    </span>
                  </td>
                  <td data-label="Why">
                    {post.rejection_reason ? (
                      <span className="muted">{post.rejection_reason}</span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td data-label="Engagement" className="money">
                    {post.total_engagement}
                  </td>
                  <td data-label="Actions">
                    <div className="ops-actions">
                      <button
                        className="btn btn-outline btn-sm"
                        onClick={() => setTarget({ post, mode: "approve" })}
                      >
                        Approve
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => setTarget({ post, mode: "reject" })}
                      >
                        Reject
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
          {list.count} post{list.count === 1 ? "" : "s"} · showing {rows.length}
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
          target?.mode === "reject"
            ? `Reject post ${target?.post.external_post_id.slice(-8)}?`
            : `Approve post ${target?.post.external_post_id.slice(-8)}?`
        }
        description={
          target?.mode === "reject"
            ? "The creator sees this reason on their dashboard. The reward is not calculated."
            : "Marks the post VERIFIED. The reward engine calculates the payout separately — approving here does not pay anything by itself."
        }
        options={target?.mode === "reject" ? REJECTION_OPTIONS : undefined}
        optionsLabel="Failure state"
        reasonLabel="Reason"
        reasonRequired={target?.mode === "reject"}
        reasonPlaceholder="Shown to the creator"
        confirmLabel={target?.mode === "reject" ? "Reject" : "Approve"}
        danger={target?.mode === "reject"}
        busy={busy}
        error={actionError}
        onCancel={() => {
          setTarget(null);
          setActionError(null);
        }}
        onConfirm={(reason, rejection) => {
          if (target) void apply(target.post, target.mode, reason, rejection);
        }}
      />
    </>
  );
}
