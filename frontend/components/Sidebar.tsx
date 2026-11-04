"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import BrandLogo from "@/lib/brand";
import { CloseIcon, LogOutIcon, PanelLeftIcon } from "@/components/icons";
import {
  BRAND_NAV,
  CREATOR_NAV,
  STAFF_NAV,
  SUPPORT_NAV,
  type NavGroup,
} from "@/lib/nav";
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
  const pathname = usePathname();

  const groups: NavGroup[] = [...CREATOR_NAV, ...(user ? BRAND_NAV : []), ...SUPPORT_NAV, ...(user?.is_staff ? STAFF_NAV : [])];

  // Which item wins: the longest href that prefixes the current path.
  const allHrefs = groups.flatMap((group) =>
    group.items.flatMap((item) => [item.href, ...(item.match ?? [])])
  );
  const activeHref = allHrefs
    .filter((href) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.length - a.length)[0];

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
        {groups.map((group, index) => (
          <div className="nav-group" key={group.label ?? `group-${index}`}>
            {group.label ? <div className="nav-group-label">{group.label}</div> : null}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = item.href === activeHref;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  className={`nav-item ${active ? "is-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                  data-tip={collapsed ? item.label : undefined}
                >
                  <Icon size={18} />
                  <span className="nav-label">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
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
          <Link href="/dashboard" className="btn btn-primary btn-block btn-sm" onClick={onClose}>
            Get started
          </Link>
        )}
      </div>
    </aside>
  );
}
