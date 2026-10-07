"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getMyPosts } from "@/services/social";
import type { SellerDashboard, SocialPost } from "@/types";

/**
 * Verification statuses still being worked on by the pipeline. Anything else
 * that isn't payable is settled and rejected -- the creator's action is to fix
 * it rather than wait.
 */
const IN_FLIGHT_STATUSES = new Set([
  "DISCOVERED",
  "BASIC_VALIDATION",
  "CAMPAIGN_MATCH",
  "DUPLICATE_CHECK",
  "METRICS_PENDING",
  "PROVIDER_ERROR",
]);

/** Statuses that mean the post is payable. */
const PAYING_STATUSES = new Set([
  "VERIFIED",
  "REWARD_CALCULATED",
  "APPROVED",
]);

/** Human labels for the enum; underscores make poor reading in a UI. */
function statusLabel(status: string): string {
  return status.toLowerCase().replace(/_/g, " ");
}

/**
 * One row of the creator's posts.
 *
 * The reason is the payload: a creator who sees `rejection_reason` can fix what
 * went wrong, while a bare status code leaves them guessing. That is why the
 * backend exposes it only on `/me/posts/` -- it is the one place a creator
 * learns why something failed without asking staff.
 */
function PostRow({ post }: { post: SocialPost }) {
  const inFlight = IN_FLIGHT_STATUSES.has(post.verification_status);
  const settled = !inFlight;
  const rejected = settled && !PAYING_STATUSES.has(post.verification_status);
  const badgeClass = rejected ? "" : inFlight ? "badge-token" : "badge-ok";

  return (
    <tr>
      <td>
        <a href={post.post_url} target="_blank" rel="noopener noreferrer">
          {post.platform} · {post.external_post_id.slice(-8)}
        </a>
      </td>
      <td>{post.campaign ?? <span className="muted">—</span>}</td>
      <td>
        <span className={`badge ${badgeClass}`}>
          {statusLabel(post.verification_status)}
        </span>
      </td>
      <td>
        {post.rejection_reason ? (
          <span className="muted">{post.rejection_reason}</span>
        ) : inFlight ? (
          <span className="muted">Verification in progress.</span>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="money">{post.total_engagement}</td>
    </tr>
  );
}

export default function DashboardPage() {
  const { user, loading, loadDashboard } = useAuth();
  const [dashboard, setDashboard] = useState<SellerDashboard | null>(null);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [postsState, setPostsState] = useState<
    "loading" | "ready" | "error"
  >("loading");

  useEffect(() => {
    if (user) {
      loadDashboard()
        .then(setDashboard)
        .catch(() => setDashboard(null));
    }
  }, [user, loadDashboard]);

  // Separate call: the dashboard is aggregate counts, this is per-post detail.
  useEffect(() => {
    if (!user) return;
    getMyPosts()
      .then((data) => {
        setPosts(data);
        setPostsState("ready");
      })
      .catch(() => setPostsState("error"));
  }, [user]);

  if (loading) {
    return (
      <div className="container section">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container section">
        <div className="card">
          <h1>Seller dashboard</h1>
          <p className="muted">
            Create an account to get a seller code, join campaigns, and track
            your rewards.
          </p>
          <div className="row">
            <Link href="/dashboard/onboard" className="btn btn-primary">
              Onboard a Seller
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="container section">
        <h1>Dashboard</h1>
        <p className="muted">
          No dashboard data yet. Complete onboarding to get started.
        </p>
        <Link href="/dashboard/onboard" className="btn btn-primary">
          Continue onboarding
        </Link>
      </div>
    );
  }

  const cards = [
    { label: "Total earnings", value: dashboard.total_earnings },
    { label: "Available to claim", value: dashboard.available_to_claim },
    { label: "Pending rewards", value: String(dashboard.pending_rewards) },
    { label: "Posts tracked", value: String(dashboard.posts_tracked) },
    { label: "Verified posts", value: String(dashboard.verified_posts) },
    { label: "Total engagement", value: String(dashboard.total_engagement) },
  ];

  return (
    <div className="container section">
      <h1>Seller dashboard</h1>
      <p className="muted">@{user.username}</p>

      <div className="stat-strip">
        {cards.map((card) => (
          <div className="stat-box" key={card.label}>
            <div className="num">{card.value}</div>
            <div className="muted">{card.label}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <h3>Your seller code</h3>
        <p>
          <code className="wallet-chip">{dashboard.seller.seller_code}</code>{" "}
          <span className="muted">
            Include it where campaign rules require a tracking code.
          </span>
        </p>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3>Your posts</h3>
          <Link href="/campaigns" className="btn btn-outline btn-sm">
            Browse campaigns
          </Link>
        </div>
        <p className="muted">
          Verification status for every post we found. A rejected post shows why,
          so you can correct it rather than guess.
        </p>

        {postsState === "loading" && <p className="muted">Loading your posts…</p>}
        {postsState === "error" && (
          <div className="banner banner-error">
            Could not load your posts. Refresh to try again.
          </div>
        )}
        {postsState === "ready" && posts.length === 0 && (
          <p className="muted">
            No posts found yet. Link your social account, publish, and it appears
            here once discovered.
          </p>
        )}
        {postsState === "ready" && posts.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Post</th>
                  <th>Campaign</th>
                  <th>Status</th>
                  <th>Why</th>
                  <th>Engagement</th>
                </tr>
              </thead>
              <tbody>
                {posts.map((post) => (
                  <PostRow key={post.id} post={post} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-3" style={{ marginTop: 20 }}>
        <div className="card">
          <h3>Active campaigns</h3>
          <p className="muted">Campaigns you have joined appear here.</p>
          <Link href="/campaigns" className="btn btn-outline btn-sm">
            Browse campaigns
          </Link>
        </div>
        <div className="card">
          <h3>Social accounts</h3>
          <p className="muted">
            Link the platforms you publish on so we can find your posts.
          </p>
          <Link href="/dashboard/onboard" className="btn btn-outline btn-sm">
            Manage connections
          </Link>
        </div>
        <div className="card">
          <h3>Wallet activity</h3>
          <p className="muted">Claims and on-chain transactions.</p>
          <Link href="/wallet" className="btn btn-outline btn-sm">
            Manage wallet
          </Link>
        </div>
      </div>
    </div>
  );
}