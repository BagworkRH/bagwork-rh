/**
 * Sidebar navigation.
 *
 * Mapped to routes that actually exist and do something — no placeholder
 * destinations. A creator sees their work; a brand sees the funding side; staff
 * see the console. Nothing here is invented for the sake of a fuller menu.
 *
 * `match` is the list of path prefixes that should light an item up; the sidebar
 * picks the longest match, so `/dashboard/onboard` highlights "Connections"
 * rather than also highlighting "Dashboard".
 */
import type { ComponentType } from "react";

import {
  CompassIcon,
  DashboardIcon,
  HelpIcon,
  MegaphoneIcon,
  PlusCircleIcon,
  ShieldIcon,
  TrophyIcon,
  UsersIcon,
  WalletIcon,
} from "@/components/icons";

export type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  /** Extra prefixes that keep this item active (e.g. detail routes). */
  match?: string[];
};

export type NavGroup = {
  label?: string;
  items: NavItem[];
};

/** The creator's working set. */
export const CREATOR_NAV: NavGroup[] = [
  {
    items: [{ href: "/dashboard", label: "Dashboard", icon: DashboardIcon }],
  },
  {
    label: "Earn",
    items: [
      { href: "/campaigns", label: "Discover campaigns", icon: CompassIcon, match: ["/campaigns"] },
      { href: "/leaderboard", label: "Leaderboard", icon: TrophyIcon, match: ["/leaderboard"] },
      { href: "/wallet", label: "Earnings & wallet", icon: WalletIcon },
    ],
  },
  {
    label: "Account",
    items: [
      { href: "/dashboard/onboard", label: "Profile & connections", icon: UsersIcon },
    ],
  },
];

/** The brand's funding side. */
export const BRAND_NAV: NavGroup[] = [
  {
    label: "Brand",
    items: [
      { href: "/brand", label: "Brand overview", icon: MegaphoneIcon, match: ["/brand"] },
      { href: "/brand/create", label: "Create campaign", icon: PlusCircleIcon },
    ],
  },
];

/** Support is always present; the console only for staff. */
export const SUPPORT_NAV: NavGroup[] = [
  {
    label: "Support",
    items: [{ href: "/help", label: "Help & support", icon: HelpIcon, match: ["/help"] }],
  },
];

export const STAFF_NAV: NavGroup[] = [
  {
    label: "Staff",
    items: [{ href: "/ops", label: "Ops console", icon: ShieldIcon, match: ["/ops"] }],
  },
];
