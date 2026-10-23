"use client";

import { useEffect } from "react";

/**
 * Blocking error dialog for failures the user has to act on — creating an
 * account, connecting a wallet, joining a campaign.
 *
 * These used to render as a banner at the bottom of the page, which is exactly
 * where nobody looks: the form sits at the top, so a failed submit looked like
 * nothing had happened at all and the user clicked again. A modal puts the
 * reason where the click was.
 */
export default function ErrorModal({
  message,
  title = "Something went wrong",
  onClose,
}: {
  message: string | null;
  title?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!message) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="error-modal-title"
      onClick={onClose}
    >
      {/* Clicks inside the dialog must not dismiss it. */}
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h3 id="error-modal-title">{title}</h3>
        <p className="modal-message">{message}</p>
        <div className="actions">
          <button className="btn btn-primary" onClick={onClose} autoFocus>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
