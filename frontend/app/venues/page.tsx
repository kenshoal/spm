import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { layoutLabel, listVenues } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../components/app-shell";

async function VenueData() {
  const result = await listVenues().then((venues) => ({ venues, failed: false as const })).catch((error: unknown) => {
    unstable_rethrow(error);
    return { venues: [], failed: true as const };
  });
  if (result.failed) {
    return <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The venue service is unavailable. Start the local API on port 8004, then refresh.</div>;
  }
  if (result.venues.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No venues yet. Add the first venue to the catalogue.</p>;
  }
  return (
    <div className="space-y-3">
      {result.venues.map((venue) => (
        <article key={venue.id} aria-labelledby={`venue-${venue.id}`} className="flex flex-col gap-3 rounded-2xl border border-[#dce4e0] bg-white p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h2 id={`venue-${venue.id}`} className="text-lg font-bold text-[#1b2b25]">{venue.name}</h2>
              <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${venue.status === "available" ? "bg-[#e3f2ea] text-[#145c40]" : "bg-[#fdecea] text-[#8c3a2b]"}`}>{venue.status === "available" ? "Available" : "Blocked"}</span>
            </div>
            <p className="mt-1 text-sm text-[#68776f]">{venue.location} · up to {venue.max_capacity} people · {venue.operating_slots.join(", ")}</p>
            <p className="mt-1 text-xs text-[#718078]">Layouts: {venue.supported_layouts.map(layoutLabel).join(", ") || "none recorded"} · Facilities: {venue.facilities.join(", ") || "none recorded"} · Accessibility: {venue.accessibility_features.join(", ") || "none recorded"}</p>
          </div>
          <Link href={`/venues/${venue.id}/edit`} className="text-sm font-semibold text-[#0f6b5b] hover:underline">Edit {venue.name}</Link>
        </article>
      ))}
    </div>
  );
}

export default async function VenuesPage() {
  const user = await requireRole("venue_staff");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Venue workspace</p>
          <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Venue catalogue</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Keep each venue&rsquo;s details accurate so coordinators plan against the real space.</p>
        </div>
        <Link href="/venues/new" className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d]">+ Add venue</Link>
      </div>
      <Suspense fallback={<div aria-label="Loading venues" className="h-36 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />}>
        <VenueData />
      </Suspense>
    </AppShell>
  );
}
