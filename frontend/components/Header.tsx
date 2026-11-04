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
 */
export default function Header() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const pathname = usePathname();
  const headerRef = useRef<HTMLElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  // Close the drawer on navigation: it overlays the page, so leaving it open
  // would hide the content the user just asked for.
  useEffect(() => {
    setMenuOpen(false);
    setProfileOpen(false);
  }, [pathname]);

  // Escape, or a tap outside, closes whichever panel is open — what a touch
  // user expects from a menu with no close control of its own.
  useEffect(() => {
    if (!menuOpen && !profileOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        setProfileOpen(false);
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (headerRef.current && !headerRef.current.contains(target)) {
        setMenuOpen(false);
        setProfileOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, [menuOpen, profileOpen]);

  return (
    <header className="site-header" ref={headerRef}>
      <div className="container header-inner">
        <Link href="/" className="brand" aria-label="bagworkRH home">
          <BrandLogo size={28} />
        </Link>

        <nav
          id="primary-nav"
          className={`nav ${menuOpen ? "nav-open" : ""}`}
          aria-label="Primary"
        >
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href} onClick={() => setMenuOpen(false)}>
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
            aria-controls="primary-nav"
            onClick={() => setMenuOpen((value) => !value)}
          >
            {menuOpen ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
          </button>
        </div>
      </div>
    </header>
  );
}
