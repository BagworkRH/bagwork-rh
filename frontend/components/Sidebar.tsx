"use client";

import Link from "next/link";

import BrandLogo from "@/lib/brand";
import { CloseIcon, LogOutIcon, PanelLeftIcon, UserIcon } from "@/components/icons";
import NavGroups from "@/components/NavGroups";
import type { User } from "@/types";

/**
 * The permanent left sidebar.
 *
 * Active state is resolved by longest matching prefix, so a detail route
 * (`/dashboard/onboard`) lights "Profile & connections" rather than also
 * lighting "Dashboard". On desktop it collapses to an icon rail; under 1024px
 * it becomes an off-canvas drawer (see the media queries in globals.css).
 */
export default function Sidebar({
  user,
  open,
  collapsed,
  onToggleCollapse,
  onClose,
  onLogout,
}: {
  user: User | null;
  open: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onClose: () => void;
  onLogout: () => void;
}) {
  return (
    <aside
      className={`sidebar ${open ? "is-open" : ""} ${collapsed ? "is-collapsed" : ""}`}
      aria-label="Primary"
    >
      <div className="sidebar-brand">
        <Link href="/" aria-label="bagworkRH home" onClick={onClose}>
          <BrandLogo size={26} />
        </Link>
        <button
          className="sidebar-collapse"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <PanelLeftIcon size={18} />
        </button>
        <button className="sidebar-close" onClick={onClose} aria-label="Close menu">
          <CloseIcon size={18} />
        </button>
      </div>

      <nav>
        <NavGroups user={user} onNavigate={onClose} collapsed={collapsed} />
      </nav>

      <div className="sidebar-foot">
        {user ? (
          <div className="sidebar-user">
            <span className="avatar avatar-sm" aria-hidden="true">
              {user.username.slice(0, 2).toUpperCase()}
            </span>
            <div className="who">
              <div className="name">{user.username}</div>
              <div className="sub">{user.is_staff ? "Staff" : "Creator"}</div>
            </div>
            <button
              className="sidebar-collapse"
              onClick={onLogout}
              aria-label="Log out"
              title="Log out"
            >
              <LogOutIcon size={16} />
            </button>
          </div>
        ) : (
          <Link href="/dashboard/onboard" className="nav-item" onClick={onClose}>
            <UserIcon size={18} />
            <span className="nav-label">Sign in / Sign up</span>
          </Link>
        )}
      </div>
    </aside>
  );
}
