"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import BrandLogo from "@/lib/brand";
import { NAV_LINKS } from "@/lib/constants";
import { useAuth } from "@/hooks/useAuth";
import { useWallet } from "@/hooks/useWallet";
import { shortenAddress } from "@/lib/constants";

export default function Header() {
  const { user, logout } = useAuth();
  const { connection, connect, error } = useWallet();
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();
  const headerRef = useRef<HTMLElement>(null);

  // Close the drawer on navigation: it overlays the page, so leaving it open
  // would hide the content the user just asked for.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Escape, or a tap outside the bar, closes it — what a touch user expects from
  // a menu with no close control of its own.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    const onPointerDown = (event: PointerEvent) => {
      if (headerRef.current && !headerRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, [menuOpen]);

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
          {connection.status === "connected" ? (
            <span className="wallet-chip" title={connection.address}>
              {shortenAddress(connection.address)}
            </span>
          ) : (
            <button className="btn btn-outline btn-sm" onClick={() => void connect()}>
              Connect Wallet
            </button>
          )}

          {user ? (
            <>
              {user.is_staff ? (
                <Link href="/ops" className="btn btn-outline btn-sm">
                  Ops
                </Link>
              ) : null}
              <button className="btn btn-ghost btn-sm" onClick={() => void logout()}>
                Log out
              </button>
            </>
          ) : (
            <Link href="/dashboard" className="btn btn-primary btn-sm">
              Onboard
            </Link>
          )}

          <button
            className="menu-toggle"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="primary-nav"
            onClick={() => setMenuOpen((v) => !v)}
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>
      </div>
      {error && connection.status === "disconnected" && (
        <div className="banner banner-error container">{error}</div>
      )}
    </header>
  );
}