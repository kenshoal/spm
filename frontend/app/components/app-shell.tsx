import Link from "next/link";
import type { ReactNode } from "react";
import { logout } from "../auth/actions";

export interface NavLink {
  href: string;
  label: string;
}

// Workspace links follow the verified session's roles, so a multi-role
// account sees every workspace it can actually use.
export function workspaceLinks(roles: string[]): NavLink[] {
  const links: NavLink[] = [];
  if (roles.includes("event_organiser")) {
    links.push({ href: "/event-requests", label: "My event requests" });
  }
  if (roles.includes("event_coordinator")) {
    links.push({ href: "/coordination/requests", label: "Coordination" });
  }
  if (roles.includes("event_operations_manager")) {
    links.push({ href: "/operations/assignments", label: "Assignments" });
  }
  if (roles.includes("venue_staff")) {
    links.push({ href: "/venues", label: "Venues" });
    links.push({ href: "/venue-blocks", label: "Venue blocks" });
  }
  if (roles.includes("event_coordinator") || roles.includes("venue_staff")) {
    links.push({ href: "/venues/search", label: "Venue search" });
  }
  if (roles.includes("technical_support")) {
    links.push({ href: "/equipment", label: "Equipment" });
  }
  // Last, so the logo (the first link) still opens the user's main workspace.
  if (links.length > 0) {
    links.push({ href: "/notifications", label: "Notifications" });
  }
  return links;
}

export function AppShell({
  children,
  signedIn = false,
  navLinks = [],
}: {
  children: ReactNode;
  signedIn?: boolean;
  navLinks?: NavLink[];
}) {
  return (
    <div className="min-h-screen bg-[#f6f8f7]">
      <header className="border-b border-[#dce4e0] bg-white">
        <div className="mx-auto flex h-17 max-w-7xl items-center justify-between px-5 sm:px-8">
          <div className="flex items-center gap-6">
            <Link href={navLinks[0]?.href ?? "/"} className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-xl bg-[#0f6b5b] text-sm font-bold text-white shadow-sm">CS</span>
              <span className="text-lg font-bold tracking-[-0.02em] text-[#17211d]">ConnectSphere</span>
            </Link>
            {navLinks.length > 0 && (
              <nav aria-label="Workspaces" className="hidden items-center gap-5 sm:flex">
                {navLinks.map((link) => (
                  <Link key={link.href} href={link.href} className="text-sm font-semibold text-[#273832] transition hover:text-[#0f6b5b]">
                    {link.label}
                  </Link>
                ))}
              </nav>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Link href="/auth" className="text-sm font-semibold text-[#0f6b5b] hover:underline">Account</Link>
            {signedIn && <form action={logout}><button type="submit" className="text-sm font-semibold text-[#6d3b35] hover:underline">Log out</button></form>}
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-[#273832]">ConnectSphere user</p>
              <p className="text-xs text-[#718078]">Role-based workspace</p>
            </div>
            <span className="grid size-9 place-items-center rounded-full bg-[#e2f1ec] text-sm font-bold text-[#0f6b5b]">CS</span>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-11">{children}</main>
    </div>
  );
}
