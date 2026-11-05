"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import Footer from "@/components/Footer";
import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import { useAuth } from "@/hooks/useAuth";

/**
 * Which surface a route belongs to.
 *
 * The product has two shells: a public marketing one (home, legal, help, share
 * cards) and the signed-in app (sidebar + topbar). Rather than move every
 * route into a route group, the split is a single list here — one place to read,
 * one place to change. Public routes keep the marketing header/footer; anything
 * under these prefixes gets the application shell.
 */
const APP_PREFIXES = [
  "/dashboard",
  "/wallet",
  "/brand",
  "/campaigns",
  "/leaderboard",
  "/creators",
  "/ops",
];

function isAppRoute(pathname: string): boolean {
  return APP_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

const COLLAPSE_KEY = "bagwork_sidebar_collapsed";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // The drawer overlays the page, so leaving it open would hide the content
  // the user just navigated to.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // Collapse is a preference, so it survives a reload.
  useEffect(() => {
    if (window.localStorage.getItem(COLLAPSE_KEY) === "1") setCollapsed(true);
  }, []);

  // Hold the page still behind the drawer rather than letting it scroll away.
  useEffect(() => {
    if (!drawerOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [drawerOpen]);

  function toggleCollapse() {
    setCollapsed((value) => {
      const next = !value;
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }

  if (!isAppRoute(pathname)) {
    return (
      <>
        <Header />
        <main className="main">{children}</main>
        <Footer />
      </>
    );
  }

  return (
    <div className="shell">
      <div className="shell-body">
        <Sidebar
          user={user}
          open={drawerOpen}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapse}
          onClose={() => setDrawerOpen(false)}
          onLogout={() => void logout()}
        />
        {drawerOpen ? (
          <button
            className="shell-scrim"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
          />
        ) : null}
        <div className="shell-main">
          <Topbar
            user={user}
            onLogout={() => void logout()}
            onOpenSidebar={() => setDrawerOpen(true)}
          />
          <main className="shell-content">{children}</main>
        </div>
      </div>
    </div>
  );
}
