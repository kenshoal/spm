import { unstable_rethrow } from "next/navigation";
import type { ReactNode } from "react";
import { requireAnyRole } from "@/lib/auth";
import { currentMonth } from "@/lib/block-calendar";
import { getVenueCalendar, parseCalendarMonth } from "@/lib/venue-calendar";
import { listVenues, type Venue } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { AvailabilityCalendarTable } from "./availability-calendar";

const inputClass = "mt-1 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 py-2.5 text-sm text-[#273832]";

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function Alert({ children }: { children: ReactNode }) {
  return <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">{children}</div>;
}

async function load<T>(promise: Promise<T>): Promise<{ value: T; failed: false } | { value: null; failed: true }> {
  return promise.then((value) => ({ value, failed: false as const })).catch((error: unknown) => {
    unstable_rethrow(error);
    return { value: null, failed: true as const };
  });
}

function VenuePicker({ venues, selected, month }: { venues: Venue[]; selected: string; month: string }) {
  return (
    <form method="get" action="/venues/availability" className="mb-6 flex flex-wrap items-end gap-3 rounded-2xl border border-[#dce4e0] bg-white p-5">
      <label className="min-w-64 flex-1 text-sm font-semibold text-[#34463f]">Show availability for
        <select name="venue" defaultValue={selected} className={inputClass}>
          {venues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name}</option>)}
        </select>
      </label>
      <input type="hidden" name="month" value={month} />
      <button type="submit" className="min-h-11 rounded-xl border border-[#0f6b5b] px-5 text-sm font-bold text-[#0f6b5b] hover:bg-[#e3f2ea]">Show</button>
    </form>
  );
}

async function AvailabilityContent({ params }: { params: Record<string, string | string[] | undefined> }) {
  const venues = await load(listVenues());
  if (venues.failed) return <Alert>The venue service is unavailable. Start the local API on port 8004, then refresh.</Alert>;
  if (venues.value.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No venues in the catalogue yet.</p>;
  }

  const month = parseCalendarMonth(first(params.month), currentMonth());
  const selectedId = first(params.venue) || venues.value[0].id;
  const picker = <VenuePicker venues={venues.value} selected={selectedId} month={month} />;
  const venue = venues.value.find((candidate) => candidate.id === selectedId);
  if (!venue) return <>{picker}<h2 className="text-xl font-bold">Venue not found</h2></>;

  const calendar = await load(getVenueCalendar(venue.id, month));
  // Never fall back to an all-available calendar when the real one is unknown.
  if (calendar.failed) return <>{picker}<Alert>The availability could not be loaded. Refresh to try again.</Alert></>;
  if (calendar.value === null) return <>{picker}<h2 className="text-xl font-bold">Venue not found</h2></>;
  return <>{picker}<AvailabilityCalendarTable calendar={calendar.value} venueId={venue.id} venueName={venue.name} /></>;
}

export default async function VenueAvailabilityPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireAnyRole(["event_coordinator", "venue_staff", "safety_officer"]);
  const params = await searchParams;
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Venue availability</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">When is a venue free?</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Each date shows the times that are booked, blocked or free between 07:00 and 24:00. Booked times include the venue&apos;s setup and turnaround. Tentative holds are not shown yet.</p>
      </div>
      {await AvailabilityContent({ params })}
    </AppShell>
  );
}
