"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { BarSeries } from "@/components/charts";
import {
  ArrowRightIcon,
  CheckIcon,
  ClockIcon,
  CoinsIcon,
  CompassIcon,
  FileTextIcon,
  SparklesIcon,
  UsersIcon,
  WalletIcon,
} from "@/components/icons";
import { EmptyState, Skeleton, StatGridSkeleton, StatTile } from "@/components/ui";
import EarningsVisibilityToggle from "@/components/EarningsVisibilityToggle";
import { useAuth } from "@/hooks/useAuth";
import { accountStatus, postStatus, toneClass } from "@/lib/labels";
import { formatAmount } from "@/lib/money";
import { getMyCampaigns } from "@/services/campaigns";
import { getCreatorCard } from "@/services/leaderboard";
import { getConnections, getMyPosts } from "@/services/social";
import type {
  CreatorCard,
  JoinedCampaign,
  SellerDashboard,
  SocialAccount,
  SocialPost,
} from "@/types";

type LoadState = "loading" | "ready" | "error";

/** One row of the creator's posts. The reason is the payload: it is what lets
 *  a creator fix a rejected post instead of guessing. */
function PostRow({ post }: { post: SocialPost }) {
  const copy = postStatus(post.verification_status);
  const published = post.published_at
    ? new Date(post.published_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    : null;

  return (
    <tr>
      <td data-label="Post">
        <a href={post.post_url} target="_blank" rel="noopener noreferrer">
          View post
        </a>
        {published ? <span className="muted"> · {published}</span> : null}
      </td>
      <td data-label="Campaign">{post.campaign ?? <span className="muted">—</span>}</td>
      <td data-label="Status">
        <span className={toneClass(copy.tone)}>{copy.text}</span>
      </td>
      <td data-label="Why">
        {post.rejection_reason || copy.reason ? (
          <span className="muted">{post.rejection_reason || copy.reason}</span>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td data-label="Engagement" className="money">
        {post.total_engagement.toLocaleString("en-US")}
      </td>
    </tr>
  );
}

/** A recent, real activity item derived from the creator's own data. */
type ActivityItem = { id: string; title: string; meta: string; tone: "money" | "brand" | "info" };

function buildActivity(posts: SocialPost[], campaigns: JoinedCampaign[]): ActivityItem[] {
  const items: ActivityItem[] = [];
  for (const post of posts.slice(0, 12)) {
    const copy = postStatus(post.verification_status);
    const when = post.published_at
      ? new Date(post.published_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
      : "recently";
    if (copy.tone === "ok") {
      items.push({ id: `p${post.id}`, title: "A post was verified and is payable", meta: when, tone: "money" });
    } else if (copy.tone === "bad" || copy.tone === "hold") {
      items.push({
        id: `p${post.id}`,
        title: post.rejection_reason || copy.reason || "A post needs attention",
        meta: when,
        tone: "info",
      });
    }
  }
  for (const campaign of campaigns.slice(0, 6)) {
    items.push({
      id: `c${campaign.campaign_id}`,
      title: `Joined ${campaign.name}`,
      meta: new Date(campaign.joined_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" }),
      tone: "brand",
    });
  }
  return items.slice(0, 8);
}

export default function DashboardPage() {
  const { user, loading, loadDashboard } = useAuth();
  const [dashboard, setDashboard] = useState<SellerDashboard | null>(null);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [postsState, setPostsState] = useState<LoadState>("loading");
  const [campaigns, setCampaigns] = useState<JoinedCampaign[]>([]);
  const [campaignsState, setCampaignsState] = useState<LoadState>("loading");
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  /**
   * The server's rule that only verified accounts are tracked, so this panel can
   * say that an unverified account earns nothing instead of showing "Connected"
   * and leaving the creator to wonder. Read from the API rather than assumed,
   * because the rule is a setting that can be off.
   */
  const [verifiedRequired, setVerifiedRequired] = useState(false);
  const [card, setCard] = useState<CreatorCard | null>(null);

  useEffect(() => {
    if (!user) return;
    loadDashboard()
      .then(setDashboard)
      .catch(() => setDashboard(null));
  }, [user, loadDashboard]);

  useEffect(() => {
    if (!user) return;
    getMyPosts()
      .then((data) => {
        setPosts(data);
        setPostsState("ready");
      })
      .catch(() => setPostsState("error"));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    getMyCampaigns()
      .then((data) => {
        setCampaigns(data);
        setCampaignsState("ready");
      })
      .catch(() => setCampaignsState("error"));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    getConnections()
      .then((data) => {
        setAccounts(data.connections);
        setVerifiedRequired(Boolean(data.verified_accounts_required));
      })
      .catch(() => setAccounts([]));
  }, [user]);

  // The creator's own card carries a real 30-day earnings series, so the chart
  // is money that actually moved rather than a decorative curve.
  useEffect(() => {
    const code = dashboard?.seller.seller_code;
    if (!code) return;
    getCreatorCard(code)
      .then(setCard)
      .catch(() => setCard(null));
  }, [dashboard]);

  if (loading) {
    return (
      <div className="stack" style={{ gap: 20 }}>
        <div className="skeleton skeleton-line" style={{ width: 220, height: 28 }} />
        <StatGridSkeleton count={4} />
        <div className="skeleton skeleton-card" style={{ height: 260 }} />
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{ maxWidth: 640 }}>
        <EmptyState
          icon={SparklesIcon}
          title="Create your creator profile"
          action={
            <Link href="/dashboard/onboard" className="btn btn-primary">
              Get started <ArrowRightIcon size={16} />
            </Link>
          }
        >
          Sign up to earn rewards for the posts you make. It takes a couple of
          minutes to set up a profile, connect your accounts and link a wallet.
        </EmptyState>
      </div>
    );
  }

  const activity = buildActivity(posts, campaigns);
  const pendingPosts = posts.filter((post) => postStatus(post.verification_status).tone === "pending").length;

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="page-head">
        <div>
          <span className="eyebrow">Overview</span>
          <h1>Welcome back, {dashboard?.seller.display_name || user.username}</h1>
          <p className="lede">Your earnings, posts and campaigns at a glance.</p>
        </div>
        <div className="actions" style={{ marginTop: 0 }}>
          <Link href="/campaigns" className="btn btn-primary">
            <CompassIcon size={16} /> Browse campaigns
          </Link>
          <Link href="/wallet" className="btn btn-outline">
            <WalletIcon size={16} /> Wallet
          </Link>
        </div>
      </div>

      {dashboard ? (
        <div className="stat-grid">
          <StatTile
            label="Total earnings"
            value={formatAmount(dashboard.total_earnings)}
            icon={CoinsIcon}
            tone="green"
            sub="All verified rewards"
          />
          <StatTile
            label="Available to claim"
            value={formatAmount(dashboard.available_to_claim)}
            icon={WalletIcon}
            tone="brand"
            sub="Ready for on-chain claim"
          />
          <StatTile
            label="Pending rewards"
            value={dashboard.pending_rewards.toLocaleString("en-US")}
            icon={ClockIcon}
            tone="warn"
            sub="Awaiting verification"
          />
          <StatTile
            label="Posts tracked"
            value={dashboard.posts_tracked.toLocaleString("en-US")}
            icon={FileTextIcon}
            tone="blue"
            sub={`${dashboard.verified_posts.toLocaleString("en-US")} verified`}
          />
        </div>
      ) : (
        <StatGridSkeleton count={4} />
      )}

      <div className="split">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <div>
                <h3>Earnings, last 30 days</h3>
                <p className="card-sub">
                  {card
                    ? `${formatAmount(card.paid ?? "0")} ${card.best_campaign?.token_symbol ?? ""} settled in total`
                    : "From settled rewards only"}
                </p>
              </div>
              {card && card.delta_30d ? (
                <span className={`stat-trend ${Number(card.delta_30d) >= 0 ? "up" : "down"}`}>
                  {Number(card.delta_30d) >= 0 ? "▲" : "▼"} {formatAmount(card.delta_30d)} 30d
                </span>
              ) : null}
            </div>
            {card ? (
              <BarSeries values={card.series} tone="green" unit={card.best_campaign?.token_symbol} />
            ) : (
              <Skeleton lines={4} />
            )}
          </div>

          <div className="card card-flush">
            <div className="card-head card-pad" style={{ marginBottom: 0 }}>
              <div>
                <h3>Your posts</h3>
                <p className="card-sub">Every post we track, and why any of them is not payable.</p>
              </div>
              <Link href="/dashboard/onboard" className="btn btn-outline btn-sm">
                Connections
              </Link>
            </div>
            {postsState === "loading" ? (
              <div className="card-pad">
                <Skeleton lines={4} />
              </div>
            ) : postsState === "error" ? (
              <div className="card-pad">
                <div className="banner banner-error">Could not load your posts. Refresh to try again.</div>
              </div>
            ) : posts.length === 0 ? (
              <div className="card-pad">
                <EmptyState
                  icon={FileTextIcon}
                  title="No posts tracked yet"
                  action={
                    <Link href="/campaigns" className="btn btn-primary btn-sm">
                      Join a campaign
                    </Link>
                  }
                >
                  Join a campaign and publish an original post — we will find it and
                  check whether it can be paid.
                </EmptyState>
              </div>
            ) : (
              <div className="table-cards">
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
                    {posts.slice(0, 8).map((post) => (
                      <PostRow key={post.id} post={post} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h3>Recent activity</h3>
              {pendingPosts > 0 ? <span className="badge badge-warn">{pendingPosts} checking</span> : null}
            </div>
            {activity.length === 0 ? (
              <p className="muted">Nothing yet. Join a campaign to get started.</p>
            ) : (
              <ul className="activity">
                {activity.map((item) => (
                  <li key={item.id}>
                    <span className={`activity-dot tone-${item.tone}`}>
                      {item.tone === "money" ? (
                        <CheckIcon size={15} />
                      ) : item.tone === "brand" ? (
                        <CompassIcon size={15} />
                      ) : (
                        <ClockIcon size={15} />
                      )}
                    </span>
                    <div className="activity-body">
                      <div className="title">{item.title}</div>
                      <div className="meta">{item.meta}</div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <div className="card-head">
              <h3>Your campaigns</h3>
              <Link href="/campaigns" className="muted" style={{ fontSize: "0.8125rem" }}>
                Browse all
              </Link>
            </div>
            {campaignsState === "loading" ? (
              <Skeleton lines={3} />
            ) : campaignsState === "error" ? (
              <div className="banner banner-error">Could not load your campaigns.</div>
            ) : campaigns.length === 0 ? (
              <p className="muted">
                You have not joined a campaign yet. Browse the live ones to start earning.
              </p>
            ) : (
              <ul className="joined-campaigns">
                {campaigns.map((campaign) => (
                  <li key={campaign.campaign_id}>
                    <span style={{ minWidth: 0, flex: "1 1 auto" }}>
                      <Link href={`/campaigns/${campaign.slug}`}>{campaign.name}</Link>
                      <div className="muted" style={{ fontSize: "0.78rem" }}>
                        {formatAmount(campaign.reward_rate)} {campaign.token_symbol} per post
                      </div>
                    </span>
                    <span className="money" style={{ fontFamily: "var(--font-mono)" }}>
                      {formatAmount(campaign.cumulative_reward)} {campaign.token_symbol}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <div className="card-head">
              <h3>Social accounts</h3>
              <Link href="/dashboard/onboard" className="muted" style={{ fontSize: "0.8125rem" }}>
                Manage
              </Link>
            </div>
            {accounts.length === 0 ? (
              <p className="muted">Link the accounts you publish from so we can find your posts.</p>
            ) : (
              <>
                <ul className="joined-campaigns">
                  {accounts.map((account) => {
                    const state = accountStatus(account.status);
                    const unpaid = !account.is_verified && verifiedRequired;
                    return (
                      <li key={`${account.platform}-${account.username}`}>
                        <span className="row" style={{ gap: 8, flex: "1 1 auto" }}>
                          <UsersIcon size={16} />@{account.username}
                          {unpaid && (
                            <span className="badge badge-warn">Not verified</span>
                          )}
                        </span>
                        <span className={toneClass(state.needsReconnect ? "bad" : "ok")}>
                          {state.text}
                        </span>
                      </li>
                    );
                  })}
                </ul>
                {accounts.some((a) => !a.is_verified) && verifiedRequired && (
                  <p className="muted" style={{ marginTop: 12, fontSize: "0.8125rem" }}>
                    Posts are only tracked for verified accounts, so an unverified
                    one earns nothing yet. The badge is re-checked daily — verifying
                    the account is enough, with no need to reconnect.
                  </p>
                )}
              </>
            )}
          </div>

          <div className="card">
            <h3>Privacy</h3>
            <EarningsVisibilityToggle />
          </div>
        </div>
      </div>
    </div>
  );
}

