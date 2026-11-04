"use client";

import { useEffect, useMemo, useState } from "react";

import CampaignCard from "@/components/CampaignCard";
import { CompassIcon, SearchIcon } from "@/components/icons";
import { EmptyState } from "@/components/ui";
import { getMyCampaigns } from "@/services/campaigns";
import type { Campaign } from "@/types";

type SortKey = "newest" | "reward" | "budget" | "ending";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "newest", label: "Newest" },
  { key: "reward", label: "Highest reward" },
  { key: "budget", label: "Largest budget" },
  { key: "ending", label: "Ending soon" },
];

const STATUS_FILTERS = ["All", "ACTIVE", "PAUSED", "ENDED"] as const;

/**
 * The campaign marketplace: search, filter and sort over the public list.
 *
 * The list itself is server-rendered from the public endpoint; only the
 * *view* of it lives here. The seller's own memberships are layered on once,
 * client-side, where the token lives — the public payload cannot know who is
 * asking, so `joined` on it is always false.
 */
export default function CampaignsExplorer({
  campaigns,
  initialQuery = "",
}: {
  campaigns: Campaign[];
  initialQuery?: string;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("All");
  const [project, setProject] = useState("All");
  const [sort, setSort] = useState<SortKey>("newest");
  const [joinedIds, setJoinedIds] = useState<number[]>([]);

  useEffect(() => {
    let cancelled = false;
    getMyCampaigns()
      .then((mine) => {
        if (!cancelled) setJoinedIds(mine.map((c) => c.campaign_id));
      })
      .catch(() => {
        // Signed out, or the call failed: the public view is still correct, it
        // just cannot say which campaigns are already joined.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const projects = useMemo(
    () => ["All", ...Array.from(new Set(campaigns.map((c) => c.project_name))).sort()],
    [campaigns]
  );

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    const filtered = campaigns.filter((campaign) => {
      if (status !== "All" && campaign.status !== status) return false;
      if (project !== "All" && campaign.project_name !== project) return false;
      if (!term) return true;
      return (
        campaign.name.toLowerCase().includes(term) ||
        campaign.project_name.toLowerCase().includes(term) ||
        campaign.description.toLowerCase().includes(term)
      );
    });

    const sorted = [...filtered];
    sorted.sort((a, b) => {
      if (sort === "reward") return Number(b.reward_rate) - Number(a.reward_rate);
      if (sort === "budget") return Number(b.budget) - Number(a.budget);
      if (sort === "ending") return new Date(a.end_at).getTime() - new Date(b.end_at).getTime();
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return sorted;
  }, [campaigns, query, status, project, sort]);

  return (
    <>
      <div className="toolbar">
        <div className="search">
          <SearchIcon size={17} />
          <input
            type="search"
            placeholder="Search campaigns by name, brand or description…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search campaigns"
          />
        </div>
        <select value={project} onChange={(event) => setProject(event.target.value)} aria-label="Filter by brand">
          {projects.map((name) => (
            <option key={name} value={name}>
              {name === "All" ? "All brands" : name}
            </option>
          ))}
        </select>
        <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)} aria-label="Sort campaigns">
          {SORTS.map((option) => (
            <option key={option.key} value={option.key}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-chips" role="group" aria-label="Filter by status">
        {STATUS_FILTERS.map((option) => (
          <button
            key={option}
            className={`filter-chip ${status === option ? "is-active" : ""}`}
            onClick={() => setStatus(option)}
            aria-pressed={status === option}
          >
            {option === "All" ? "All statuses" : option.charAt(0) + option.slice(1).toLowerCase()}
          </button>
        ))}
        <span className="muted" style={{ alignSelf: "center", fontSize: "0.8125rem" }}>
          {visible.length} campaign{visible.length === 1 ? "" : "s"}
        </span>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={CompassIcon}
          title="No campaigns match those filters"
          action={
            <button
              className="btn btn-outline btn-sm"
              onClick={() => {
                setQuery("");
                setStatus("All");
                setProject("All");
              }}
            >
              Clear filters
            </button>
          }
        >
          Try a different search term, brand or status.
        </EmptyState>
      ) : (
        <div className="grid">
          {visible.map((campaign) => (
            <CampaignCard
              key={campaign.id}
              campaign={{ ...campaign, joined: joinedIds.includes(campaign.id) }}
            />
          ))}
        </div>
      )}
    </>
  );
}
