"use client";

import { useEffect, useRef, useState } from "react";

import { getLeaderboard } from "@/services/leaderboard";
import type { Leaderboard } from "@/types";

/** Rank bands, the way a leaderboard is actually read: who is winning, then the chase. */
export const BOARD_RANGES = [
  { label: "Top 20", limit: 20, offset: 0 },
  { label: "21–50", limit: 30, offset: 20 },
  { label: "51–100", limit: 50, offset: 50 },
] as const;

export type BoardState = "loading" | "ready" | "error";

/**
 * Board fetching, shared by the landing page and the full leaderboard.
 *
 * Two behaviours matter and are easy to get wrong twice: the first request is
 * skipped because the server already rendered the default view (so the page
 * does not flash a skeleton over real content), and a cancelled request can
 * never overwrite a newer one.
 */
export function useLeaderboardBoard(initialBoard: Leaderboard | null) {
  const [board, setBoard] = useState<Leaderboard | null>(initialBoard);
  const [state, setState] = useState<BoardState>(initialBoard ? "ready" : "loading");
  const [slug, setSlug] = useState("");
  const [rangeIndex, setRangeIndex] = useState(0);
  const firstRun = useRef(true);

  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      if (initialBoard) return;
    }
    let cancelled = false;
    setState("loading");
    const range = BOARD_RANGES[rangeIndex];
    getLeaderboard({ campaign: slug || undefined, limit: range.limit, offset: range.offset })
      .then((data) => {
        if (!cancelled) {
          setBoard(data);
          setState("ready");
        }
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [slug, rangeIndex, initialBoard]);

  return { board, state, slug, setSlug, rangeIndex, setRangeIndex };
}
