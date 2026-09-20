import Link from "next/link";
import type { ReactNode } from "react";
import { logout } from "../auth/actions";

export function AppShell({ children, signedIn = false }: { children: ReactNode; signedIn?: boolean }) {
  return (
    <div className="min-h-screen bg-[#f6f8f7]">
      <header className="border-b border-[#dce4e0] bg-white">
        <div className="mx-auto flex h-17 max-w-7xl items-center justify-between px-5 sm:px-8">
          <Link href="/event-requests" className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-[#0f6b5b] text-sm font-bold text-white shadow-sm">CS</span>
            <span className="text-lg font-bold tracking-[-0.02em] text-[#17211d]">ConnectSphere</span>
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/auth" className="text-sm font-semibold text-[#0f6b5b] hover:underline">Account</Link>
            {signedIn && <form action={logout}><button type="submit" className="text-sm font-semibold text-[#6d3b35] hover:underline">Log out</button></form>}
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-[#273832]">Event organiser</p>
              <p className="text-xs text-[#718078]">Organiser workspace</p>
            </div>
            <span className="grid size-9 place-items-center rounded-full bg-[#e2f1ec] text-sm font-bold text-[#0f6b5b]">EO</span>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-11">{children}</main>
    </div>
  );
}
