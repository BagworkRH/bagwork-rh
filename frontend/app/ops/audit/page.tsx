"use client";

import { useOpsList } from "@/hooks/useOpsList";
import { listAuditLogs } from "@/services/admin";
import type { OpsAuditEntry } from "@/types/ops";

/**
 * The append-only audit trail.
 *
 * Read-only by design: there is no endpoint that edits or deletes an entry, so
 * this screen has no actions. That is the point of it — it is the record you
 * check when something looks wrong elsewhere.
 */
export default function OpsAuditPage() {
  const list = useOpsList<OpsAuditEntry>(listAuditLogs);
  const rows = list.data?.results ?? [];

  return (
    <>
      <div className="ops-toolbar">
        <label className="field">
          <span>Action</span>
          <input
            type="search"
            placeholder="e.g. REWARD_APPROVED"
            value={String(list.filters.action ?? "")}
            onChange={(event) => list.setFilter("action", event.target.value)}
          />
        </label>
        <label className="field">
          <span>Object type</span>
          <input
            type="search"
            placeholder="e.g. Reward"
            value={String(list.filters.object_type ?? "")}
            onChange={(event) => list.setFilter("object_type", event.target.value)}
          />
        </label>
        <label className="field">
          <span>Object id</span>
          <input
            type="search"
            placeholder="e.g. 42"
            value={String(list.filters.object_id ?? "")}
            onChange={(event) => list.setFilter("object_id", event.target.value)}
          />
        </label>
        <label className="field">
          <span>Actor username</span>
          <input
            type="search"
            placeholder="who did it"
            value={String(list.filters.actor ?? "")}
            onChange={(event) => list.setFilter("actor", event.target.value)}
          />
        </label>
        <button className="btn btn-outline btn-sm" onClick={list.reload}>
          Refresh
        </button>
      </div>

      {list.state === "loading" ? <p className="muted">Loading audit log…</p> : null}
      {list.state === "error" ? <div className="banner banner-error">{list.error}</div> : null}
      {list.state === "ready" && rows.length === 0 ? (
        <p className="muted">No entries match this filter.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="table-cards">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Object</th>
                <th>Metadata</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((entry) => (
                <tr key={entry.id}>
                  <td data-label="When">{new Date(entry.created_at).toLocaleString()}</td>
                  <td data-label="Action">
                    <code>{entry.action}</code>
                  </td>
                  <td data-label="Actor">{entry.actor ?? "system"}</td>
                  <td data-label="Object">
                    {entry.object_type} {entry.object_id}
                  </td>
                  <td data-label="Metadata">
                    <span className="muted" style={{ overflowWrap: "anywhere" }}>
                      {JSON.stringify(entry.metadata)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="ops-pager">
        <span className="muted">
          {list.count} entr{list.count === 1 ? "y" : "ies"} · showing {rows.length}
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
    </>
  );
}
