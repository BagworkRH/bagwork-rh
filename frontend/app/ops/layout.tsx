"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/hooks/useAuth";

const TABS = [
  { href: "/ops", label: "Overview" },
  { href: "/ops/sellers", label: "Sellers" },
  { href: "/ops/campaigns", label: "Campaigns" },
  { href: "/ops/posts", label: "Posts" },
  { href: "/ops/rewards", label: "Rewards" },
  { href: "/ops/claims", label: "Claims" },
  { href: "/ops/risk", label: "Risk" },
  { href: "/ops/audit", label: "Audit" },
  { href: "/ops/settings", label: "Settings" },
];

/**
 * Staff console shell.
 *
 * The guard below is a courtesy, not the security boundary: every endpoint the
 * console calls is `IsAdminUser` on the server, so hiding the UI stops a
 * curious user from seeing buttons that would only 403 anyway. Nothing here is
 * load-bearing for authorisation.
 *
 * Note the path: `/ops`, not `/admin`. nginx routes `/admin/` to Django, so a
 * Next.js route there would never be reached in production.
 */
export default function OpsLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();

  if (loading) {
    return (
      <div className="container section" style={{ maxWidth: 560 }}>
        <p className="muted">Checking access…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container section" style={{ maxWidth: 560 }}>
        <h1>Staff console</h1>
        <div className="card">
          <p>Sign in with a staff account to continue.</p>
          <div className="actions">
            <Link href="/dashboard" className="btn btn-primary">
              Go to sign in
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!user.is_staff) {
    return (
      <div className="container section" style={{ maxWidth: 560 }}>
        <h1>Staff console</h1>
        <div className="card">
          <p className="muted">
            This area is restricted to staff accounts. {user.email} does not have access.
          </p>
          <div className="actions">
            <Link href="/dashboard" className="btn btn-outline">
              Back to dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container section">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 4 }}>Ops console</h1>
        <span className="badge badge-token">staff</span>
      </div>
      <p className="muted">
        Signed in as {user.email}. Every action taken here is written to the audit trail.
      </p>

      <nav className="ops-tabs" aria-label="Ops sections">
        {TABS.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={pathname === tab.href ? "ops-tab ops-tab-active" : "ops-tab"}
            aria-current={pathname === tab.href ? "page" : undefined}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {children}
    </div>
  );
}
