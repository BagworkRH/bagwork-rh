"use client";

import { useState } from "react";

/**
 * Share this card.
 *
 * Uses the platform share sheet where there is one (phones, where most sharing
 * actually happens) and falls back to copying the link. It reports what it did:
 * a share button that silently does nothing is indistinguishable from a broken
 * one, and this button's whole job is to get the link out.
 */
export default function ShareCardButton({ title }: { title: string }) {
  const [state, setState] = useState<"idle" | "copied" | "shared" | "failed">("idle");

  async function share() {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title, url });
        setState("shared");
      } else {
        await navigator.clipboard.writeText(url);
        setState("copied");
      }
    } catch {
      setState("failed");
    }
    window.setTimeout(() => setState("idle"), 2500);
  }

  const label =
    state === "copied"
      ? "Link copied"
      : state === "shared"
        ? "Shared"
        : state === "failed"
          ? "Could not share"
          : "Share this card";

  return (
    <button className="btn btn-primary btn-sm" onClick={() => void share()}>
      {label}
    </button>
  );
}
