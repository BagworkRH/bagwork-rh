"use client";

import { useCallback, useState } from "react";

import ReasonPrompt from "@/components/ops/ReasonPrompt";
import { useOpsList } from "@/hooks/useOpsList";
import { listRiskFlags, resolveRiskFlag, runRiskScan } from "@/services/admin";
import type { OpsRiskFlag } from "@/types/ops";

type Decision = "dismiss" | "confirm" | "review";

const DECISION_LABEL: Record<Decision, string> = {
  dismiss: "Dismiss",
  confirm: "Confirm",
  review: "Take into review",
};

/** Signals are the scanner's evidence; render them as readable text. */
function signalsText(signals: OpsRiskFlag["signals"]): string {
  if (Array.isArray(signals)) return signals.map(String).join(", ") || "—";
  if (signals && typeof signals === "object") {
    const parts = Object.entries(signals).map(([key, value]) => `${key}: ${String(value)}`);
    return parts.join(" · ") || "—";
  }
  return "—";
}

/**
 * Fraud and risk review queue.
 *
 * The scanner only ever queues evidence for a human; it never suspends anyone
 * on its own. Dismiss, confirm and take-into-review are the three judgements a
 * person can record here, and each one is audited.
 */
export default function OpsRiskPage() {
  const list = useOpsList<OpsRiskFlag>(listRiskFlags, { status: "OPEN" });
  const [target, setTarget] = useState<{ flag: OpsRiskFlag; decision: Decision } | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = useCallback(
    async (flag: OpsRiskFlag, decision: Decision, note: string) => {
      setBusy(true);
      setActionError(null);
      try {
        await resolveRiskFlag(flag.id, decision, note);
        setNotice(`Flag ${flag.id} ${DECISION_LABEL[decision].toLowerCase()}d.`);
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

  const scan = useCallback(async () => {
    setScanning(true);
    setActionError(null);
    try {
      await runRiskScan();
      setNotice("Scan finished. Anything new is in the queue below.");
      list.reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "The scan could not be started.");
    } finally {
      setScanning(false);
    }
  }, [list]);

  const rows = list.data?.results ?? [];
  const summary = list.data?.summary;

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
            <option value="OPEN">Open</option>
            <option value="REVIEWING">In review</option>
            <option value="DISMISSED">Dismissed</option>
            <option value="CONFIRMED">Confirmed</option>
          </select>
        </label>
        <label className="field">
          <span>Severity</span>
          <select
            value={String(list.filters.severity ?? "")}
            onChange={(event) => list.setFilter("severity", event.target.value)}
          >
            <option value="">Any</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
        </label>
        <button className="btn btn-outline btn-sm" onClick={list.reload}>
          Refresh
        </button>
        <button className="btn btn-outline btn-sm" onClick={scan} disabled={scanning}>
          {scanning ? "Scanning…" : "Run scan"}
        </button>
      </div>

      {summary ? (
        <p className="muted">
          Open: {summary.open} · high {summary.high} · medium {summary.medium} · low{" "}
          {summary.low}. Review threshold {summary.threshold}.
        </p>
      ) : null}

      {notice ? <div className="banner banner-ok">{notice}</div> : null}
      {list.state === "loading" ? <p className="muted">Loading risk flags…</p> : null}
      {list.state === "error" ? <div className="banner banner-error">{list.error}</div> : null}
      {actionError && target === null ? (
        <div className="banner banner-error">{actionError}</div>
      ) : null}
      {list.state === "ready" && rows.length === 0 ? (
        <p className="muted">Nothing flagged. An empty queue is the normal state.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="table-cards">
          <table>
            <thead>
              <tr>
                <th>Flag</th>
                <th>Seller</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((flag) => (
                <tr key={flag.id}>
                  <td data-label="Flag">
                    #{flag.id} · {flag.subject_type} {flag.subject_id}
                    <div className="muted">{signalsText(flag.signals)}</div>
                    {flag.note ? <div className="muted">note: {flag.note}</div> : null}
                  </td>
                  <td data-label="Seller">
                    <code>{flag.seller_code ?? "—"}</code>
                    <div className="muted">{new Date(flag.created_at).toLocaleDateString()}</div>
                  </td>
                  <td data-label="Severity">
                    <span className={flag.severity === "HIGH" ? "badge badge-danger" : "badge"}>
                      {flag.severity}
                    </span>
                    <div className="muted">score {flag.score}</div>
                  </td>
                  <td data-label="Status">
                    <span className="badge">{flag.status}</span>
                    {flag.resolved_by ? <div className="muted">by {flag.resolved_by}</div> : null}
                  </td>
                  <td data-label="Actions">
                    <div className="ops-actions">
                      <button
                        className="btn btn-outline btn-sm"
                        onClick={() => setTarget({ flag, decision: "review" })}
                      >
                        Review
                      </button>
                      <button
                        className="btn btn-outline btn-sm"
                        onClick={() => setTarget({ flag, decision: "dismiss" })}
                      >
                        Dismiss
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => setTarget({ flag, decision: "confirm" })}
                      >
                        Confirm
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
          {list.count} flag{list.count === 1 ? "" : "s"} · showing {rows.length}
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
          target ? `${DECISION_LABEL[target.decision]} flag #${target.flag.id}?` : "Resolve flag"
        }
        description={
          target?.decision === "confirm"
            ? "Marks the evidence as genuine. Suspending the seller is a separate, deliberate step on the Sellers tab."
            : target?.decision === "dismiss"
              ? "Marks the flag as not a concern."
              : "Marks the flag as being looked into. It stays in the queue."
        }
        reasonLabel="Note"
        reasonPlaceholder="What you found, or why you decided this"
        confirmLabel={target ? DECISION_LABEL[target.decision] : "Confirm"}
        danger={target?.decision === "confirm"}
        busy={busy}
        error={actionError}
        onCancel={() => {
          setTarget(null);
          setActionError(null);
        }}
        onConfirm={(note) => {
          if (target) void apply(target.flag, target.decision, note);
        }}
      />
    </>
  );
}
