"use client";

import { useEffect, useState } from "react";

/**
 * Confirmation dialog for staff actions that need a reason.
 *
 * Suspending a seller, pausing a campaign, rejecting a post and reversing a
 * reward all record *why* in the audit trail, so the reason is part of the
 * action rather than an afterthought. Built on the same modal styles as the
 * rest of the product, so it works on a phone as well as a desktop.
 */
export default function ReasonPrompt({
  open,
  title,
  description,
  reasonLabel = "Reason",
  reasonRequired = false,
  reasonPlaceholder,
  options,
  optionsLabel,
  confirmLabel = "Confirm",
  danger = false,
  busy = false,
  error = null,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description?: string;
  reasonLabel?: string;
  reasonRequired?: boolean;
  reasonPlaceholder?: string;
  options?: { label: string; value: string }[];
  optionsLabel?: string;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: (reason: string, option: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [option, setOption] = useState(options?.[0]?.value ?? "");

  // Fresh state each time it opens, so a previous reason cannot leak into the
  // next action.
  useEffect(() => {
    if (!open) return;
    setReason("");
    setOption(options?.[0]?.value ?? "");
  }, [open, options]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  const blocked = busy || (reasonRequired && reason.trim().length === 0);

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="reason-prompt-title"
      onClick={() => {
        if (!busy) onCancel();
      }}
    >
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h3 id="reason-prompt-title">{title}</h3>
        {description ? <p className="muted">{description}</p> : null}

        {options && options.length > 0 ? (
          <label className="field">
            <span>{optionsLabel ?? "Choose"}</span>
            <select value={option} onChange={(event) => setOption(event.target.value)}>
              {options.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <label className="field">
          <span>
            {reasonLabel}
            {reasonRequired ? "" : " (optional)"}
          </span>
          <textarea
            rows={3}
            value={reason}
            placeholder={reasonPlaceholder}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>

        {error ? <p className="modal-message">{error}</p> : null}

        <div className="actions">
          <button className="btn btn-outline" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            className={danger ? "btn btn-danger" : "btn btn-primary"}
            onClick={() => onConfirm(reason.trim(), option)}
            disabled={blocked}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
