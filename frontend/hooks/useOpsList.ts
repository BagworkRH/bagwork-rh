"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { OpsFilters } from "@/services/admin";
import type { OpsPage } from "@/types/ops";

type State = "loading" | "ready" | "error";

/**
 * Shared list state for the ops console: filters, paging, loading and errors.
 *
 * Every staff list endpoint has the same envelope (`count/limit/offset/results`),
 * so one hook covers all of them. `fetcher` must be a module-level function so
 * its identity is stable — passing an inline arrow would re-fetch on every
 * render.
 */
export function useOpsList<T>(
  fetcher: (filters: OpsFilters) => Promise<OpsPage<T>>,
  initial: OpsFilters = {}
) {
  const [filters, setFilters] = useState<OpsFilters>(initial);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<OpsPage<T> | null>(null);
  const [state, setState] = useState<State>("loading");
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const params = useMemo(() => ({ ...filters, offset }), [filters, offset]);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    fetcher(params)
      .then((page) => {
        if (cancelled) return;
        setData(page);
        setError(null);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load this list.");
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [fetcher, params, nonce]);

  const setFilter = useCallback((key: string, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    // A changed filter is a different result set, so paging restarts.
    setOffset(0);
  }, []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const limit = data?.limit ?? 50;
  const count = data?.count ?? 0;

  return {
    data,
    state,
    error,
    filters,
    setFilter,
    offset,
    setOffset,
    reload,
    count,
    limit,
    canPrev: offset > 0,
    canNext: offset + limit < count,
  };
}
