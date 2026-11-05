"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BRAND_NAV, CREATOR_NAV, STAFF_NAV, SUPPORT_NAV, type NavGroup } from "@/lib/nav";
import type { User } from "@/types";

/**
 * The navigation groups, rendered once for both shells.
 *
 * The app sidebar and the public drawer must not drift apart: they are the same
 * product navigation, and a link that appears in one and not the other is a bug
 * waiting to be reported. Active state is the longest matching prefix, so a
 * detail route lights its own item rather than also lighting its parent.
 */
export default function NavGroups({
  user,
  onNavigate,
  collapsed = false,
}: {
  user: User | null;
  onNavigate?: () => void;
  collapsed?: boolean;
}) {
  const pathname = usePathname();

  const groups: NavGroup[] = [
    ...CREATOR_NAV,
    ...(user ? BRAND_NAV : []),
    ...SUPPORT_NAV,
    ...(user?.is_staff ? STAFF_NAV : []),
  ];

  const allHrefs = groups.flatMap((group) =>
    group.items.flatMap((item) => [item.href, ...(item.match ?? [])])
  );
  const activeHref = allHrefs
    .filter((href) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.length - a.length)[0];

  return (
    <>
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
                onClick={onNavigate}
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
    </>
  );
}
