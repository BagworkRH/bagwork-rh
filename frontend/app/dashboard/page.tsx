"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import type { SellerDashboard } from "@/types";

export default function DashboardPage() {
  const { user, loading, loadDashboard } = useAuth();
  const [dashboard, setDashboard] = useState<SellerDashboard | null>(null);

  useEffect(() => {
    if (user) {
      loadDashboard()
        .then(setDashboard)
        .catch(() => setDashboard(null));
    }
  }, [user, loadDashboard]);

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

      <div className="grid grid-3" style={{ marginTop: 20 }}>
        <div className="card">
          <h3>Active campaigns</h3>
          <p className="muted">Campaigns you have joined appear here.</p>
          <Link href="/campaigns" className="btn btn-outline btn-sm">
            Browse campaigns
          </Link>
        </div>
        <div className="card">
          <h3>Recent tracked posts</h3>
          <p className="muted">Your qualifying posts and verification status.</p>
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