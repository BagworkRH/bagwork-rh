"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  BellIcon,
  ChevronDownIcon,
  DashboardIcon,
  HelpIcon,
  LogOutIcon,
  MenuIcon,
  SearchIcon,
  TrophyIcon,
  UserIcon,
  UsersIcon,
  WalletIcon,
} from "@/components/icons";
import { postStatus } from "@/lib/labels";
import { getMyPosts } from "@/services/social";
import type { SocialPost, User } from "@/types";

/** Close a popover on Escape or a click outside the element that owns it. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open, close]);
  return ref;
}

export default function Topbar({
  user,
  onLogout,
  onOpenSidebar,
}: {
  user: User | null;
  onLogout: () => void;
  onOpenSidebar: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [bellOpen, setBellOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [needsAttention, setNeedsAttention] = useState<SocialPost[]>([]);

  // Real "needs attention" items, not a decorative badge: posts the platform
  // has flagged or held. Fetched once per mount from the creator's own feed.
  useEffect(() => {
    if (!user) {
      setNeedsAttention([]);
      return;
    }
    let cancelled = false;
    getMyPosts()
      .then((posts) => {
        if (cancelled) return;
        setNeedsAttention(
          posts.filter((post) => {
            const tone = postStatus(post.verification_status).tone;
            return tone === "bad" || tone === "hold";
          })
        );
      })
      .catch(() => {
        if (!cancelled) setNeedsAttention([]);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const bellRef = useDismiss(bellOpen, () => setBellOpen(false));
  const profileRef = useDismiss(profileOpen, () => setProfileOpen(false));

  function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    const term = query.trim();
    router.push(term ? `/campaigns?q=${encodeURIComponent(term)}` : "/campaigns");
  }

  return (
    <header className="topbar">
      <button className="topbar-toggle" onClick={onOpenSidebar} aria-label="Open navigation">
        <MenuIcon size={20} />
      </button>

      <form className="topbar-search" onSubmit={submitSearch} role="search">
        <SearchIcon size={17} />
        <input
          type="search"
          placeholder="Search campaigns…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search campaigns"
        />
      </form>

      <div className="topbar-actions">
        <div className="dropdown" ref={bellRef}>
          <button
            className="icon-btn"
            onClick={() => setBellOpen((v) => !v)}
            aria-label="Notifications"
            aria-expanded={bellOpen}
          >
            <BellIcon size={19} />
            {needsAttention.length > 0 ? <span className="dot">{needsAttention.length}</span> : null}
          </button>
          {bellOpen ? (
            <div className="dropdown-menu" style={{ minWidth: 300 }}>
              <div className="dropdown-head">
                <div className="name">Needs your attention</div>
                <div className="sub">
                  {needsAttention.length > 0
                    ? `${needsAttention.length} post${needsAttention.length === 1 ? "" : "s"}`
                    : "You are all caught up"}
                </div>
              </div>
              <div className="dropdown-sep" />
              {needsAttention.length === 0 ? (
                <div className="dropdown-head sub">Nothing is waiting on you right now.</div>
              ) : (
                needsAttention.slice(0, 5).map((post) => {
                  const copy = postStatus(post.verification_status);
                  return (
                    <a
                      key={post.id}
                      className="dropdown-item"
                      href={post.post_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <span style={{ minWidth: 0 }}>
                        <span className="name" style={{ display: "block", fontSize: "0.83rem" }}>
                          {copy.text}
                        </span>
                        <span className="sub">{post.rejection_reason || copy.reason}</span>
                      </span>
                    </a>
                  );
                })
              )}
              <div className="dropdown-sep" />
              <Link className="dropdown-item" href="/dashboard" onClick={() => setBellOpen(false)}>
                <DashboardIcon size={16} /> View your posts
              </Link>
            </div>
          ) : null}
        </div>

        {user ? (
          <div className="dropdown" ref={profileRef}>
            <button
              className="profile-btn"
              onClick={() => setProfileOpen((v) => !v)}
              aria-label="Account menu"
              aria-expanded={profileOpen}
            >
              <span className="avatar avatar-sm" aria-hidden="true">
                {user.username.slice(0, 2).toUpperCase()}
              </span>
              <span className="who">
                <span className="name">{user.username}</span>
                <span className="sub">{user.is_staff ? "Staff" : "Creator"}</span>
              </span>
              <ChevronDownIcon size={15} />
            </button>
            {profileOpen ? (
              <div className="dropdown-menu">
                <div className="dropdown-head">
                  <div className="name">{user.username}</div>
                  <div className="sub">{user.email}</div>
                </div>
                <div className="dropdown-sep" />
                <Link className="dropdown-item" href="/dashboard" onClick={() => setProfileOpen(false)}>
                  <DashboardIcon size={16} /> Dashboard
                </Link>
                <Link className="dropdown-item" href="/wallet" onClick={() => setProfileOpen(false)}>
                  <WalletIcon size={16} /> Earnings &amp; wallet
                </Link>
                <Link className="dropdown-item" href="/leaderboard" onClick={() => setProfileOpen(false)}>
                  <TrophyIcon size={16} /> Leaderboard
                </Link>
                <Link className="dropdown-item" href="/dashboard/onboard" onClick={() => setProfileOpen(false)}>
                  <UsersIcon size={16} /> Profile &amp; connections
                </Link>
                <Link className="dropdown-item" href="/help" onClick={() => setProfileOpen(false)}>
                  <HelpIcon size={16} /> Help &amp; support
                </Link>
                <div className="dropdown-sep" />
                <button className="dropdown-item" onClick={onLogout}>
                  <LogOutIcon size={16} /> Log out
                </button>
              </div>
            ) : null}
          </div>
        ) : (
          <Link
            href="/dashboard/onboard"
            className="icon-btn"
            aria-label="Sign in or create an account"
            title="Sign in / Sign up"
          >
            <UserIcon size={19} />
          </Link>
        )}
      </div>
    </header>
  );
}
