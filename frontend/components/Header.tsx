"use client";

import Link from "next/link";
import { useState } from "react";
import { BRAND_NAME, NAV_LINKS } from "@/lib/constants";
import { useAuth } from "@/hooks/useAuth";
import { useWallet } from "@/hooks/useWallet";
import { shortenAddress } from "@/lib/constants";

export default function Header() {
  const { user, logout } = useAuth();
  const { connection, connect, error } = useWallet();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">◆</span> {BRAND_NAME}
        </Link>

        <nav className={`nav ${menuOpen ? "nav-open" : ""}`} aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href} onClick={() => setMenuOpen(false)}>
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="header-actions">
          {connection.status === "connected" ? (
            <span className="wallet-chip" title={`Chain ${connection.chainId}`}>
              {shortenAddress(connection.address)}
            </span>
          ) : (
            <button className="btn btn-outline btn-sm" onClick={() => void connect()}>
              Connect Wallet
            </button>
          )}

          {user ? (
            <button className="btn btn-ghost btn-sm" onClick={() => void logout()}>
              Log out
            </button>
          ) : (
            <Link href="/dashboard" className="btn btn-primary btn-sm">
              Onboard
            </Link>
          )}

          <button
            className="menu-toggle"
            aria-label="Toggle menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            ☰
          </button>
        </div>
      </div>
      {error && connection.status === "disconnected" && (
        <div className="banner banner-error container">{error}</div>
      )}
    </header>
  );
}