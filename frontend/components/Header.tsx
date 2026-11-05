"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  ChevronDownIcon,
  CloseIcon,
  DashboardIcon,
  LogOutIcon,
  MenuIcon,
  ShieldIcon,
  UserIcon,
  WalletIcon,
} from "@/components/icons";
import NavGroups from "@/components/NavGroups";
import BrandLogo from "@/lib/brand";
import { NAV_LINKS } from "@/lib/constants";
import { useAuth } from "@/hooks/useAuth";

/**
 * The public header.
 *
 * There is no wallet control here and no sign-up button. A visitor gets one
 * profile control: signed out it opens the sign-up page, signed in it opens an
 * account menu. Connecting a wallet belongs after sign-up, on the profile page —
 * offering "Connect Wallet" to someone with no account asks them to do the
 * second step before the first.
 *
 * On a phone the burger opens the same full-height drawer the signed-in app
 * uses, with the same grouped navigation. The drawer is rendered *outside*
 * `<header>` deliberately: the header's `backdrop-filter` would otherwise become
 * the containing block for a fixed-position child and clip it to the bar.
 */
export default function Header() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const pathname = usePathname();
  const profileRef = useRef<HTMLDivElement>(null);

  // Close everything on navigation: the drawer overlays the page, so leaving it
  // open would hide the content the user just asked for.
  useEffect(() => {
    setMenuOpen(false);
    setProfileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen && !profileOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        setProfileOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen, profileOpen]);

  // The drawer has its own scrim; only the profile menu needs an outside click.
  useEffect(() => {
    if (!profileOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [profileOpen]);

  // Hold the page still behind the drawer rather than letting it scroll away.
  useEffect(() => {
    if (!menuOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [menuOpen]);

  return (
    <>
      <header className="site-header">
        <div className="container header-inner">
          <Link href="/" className="brand" aria-label="bagworkRH home">
            <BrandLogo size={28} />
          </Link>

          <nav className="nav" aria-label="Primary">
            {NAV_LINKS.map((link) => (
              <Link key={link.href} href={link.href}>
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="header-actions">
            {user ? (
              <div className="dropdown" ref={profileRef}>
                <button
                  className="profile-btn"
                  onClick={() => setProfileOpen((value) => !value)}
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
                    <Link className="dropdown-item" href="/dashboard/onboard" onClick={() => setProfileOpen(false)}>
                      <UserIcon size={16} /> Profile &amp; wallet
                    </Link>
                    {user.is_staff ? (
                      <Link className="dropdown-item" href="/ops" onClick={() => setProfileOpen(false)}>
                        <ShieldIcon size={16} /> Ops console
                      </Link>
                    ) : null}
                    <div className="dropdown-sep" />
                    <button className="dropdown-item" onClick={() => void logout()}>
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

            <button
              className="menu-toggle"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((value) => !value)}
            >
              {menuOpen ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
            </button>
          </div>
        </div>
      </header>

      {menuOpen ? (
        <button className="shell-scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />
      ) : null}

      <aside
        className={`sidebar nav-drawer ${menuOpen ? "is-open" : ""}`}
        aria-label="Menu"
        aria-hidden={!menuOpen}
      >
        <div className="sidebar-brand">
          <Link href="/" aria-label="bagworkRH home" onClick={() => setMenuOpen(false)}>
            <BrandLogo size={26} />
          </Link>
          <button className="sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <CloseIcon size={18} />
          </button>
        </div>

        <nav>
          <NavGroups user={user} onNavigate={() => setMenuOpen(false)} />
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
                onClick={() => void logout()}
                aria-label="Log out"
                title="Log out"
              >
                <LogOutIcon size={16} />
              </button>
            </div>
          ) : (
            <Link href="/dashboard/onboard" className="nav-item" onClick={() => setMenuOpen(false)}>
              <UserIcon size={18} />
              <span className="nav-label">Sign in / Sign up</span>
            </Link>
          )}
        </div>
      </aside>
    </>
  );
}
