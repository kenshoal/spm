import { unstable_rethrow } from "next/navigation";
import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth";
import { bookingsAffectedBy, buildBlockCalendar, currentDate, currentMonth, parseMonth } from "@/lib/block-calendar";
import type { VenueBlock } from "@/lib/venue-block-options";
import type { VenueBooking } from "@/lib/venue-booking-options";
import { listApprovedBookings } from "@/lib/venue-bookings";
import { listVenueBlocks } from "@/lib/venue-blocks";
import { listVenues, type Venue } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../components/app-shell";
import { BlockCalendarTable } from "./block-calendar";
import { BlockForm } from "./block-form";
import { BlockList } from "./block-list";

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

function formatDay(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function savedMessage(affected: VenueBooking[]): string {
  if (affected.length === 0) return "Block saved.";
  const list = affected
    .map((booking) => `${booking.event_name ?? "Untitled event"} (${formatDay(booking.start_date)} – ${formatDay(booking.end_date)})`)
    .join("; ");
  const plural = affected.length > 1;
  return `Block saved. It affects ${affected.length} confirmed booking${plural ? "s" : ""}: ${list}. ${plural ? "Their Coordinators have" : "Its Coordinator has"} been notified.`;
}

function VenuePicker({ venues, selected, month }: { venues: Venue[]; selected: string; month: string }) {
  return (
    <form method="get" action="/venue-blocks" className="mb-6 flex flex-wrap items-end gap-3 rounded-2xl border border-[#dce4e0] bg-white p-5">
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

async function VenueBlocksContent({ params }: { params: Record<string, string | string[] | undefined> }) {
  const venues = await load(listVenues());
  if (venues.failed) {
    return <Alert>The venue service is unavailable. Start the local API on port 8004, then refresh.</Alert>;
  }
  if (venues.value.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No venues in the catalogue yet.</p>;
  }

  const month = parseMonth(first(params.month), currentMonth());
  const selectedId = first(params.venue) || venues.value[0].id;
  const picker = <VenuePicker venues={venues.value} selected={selectedId} month={month} />;
  const notFound = <>{picker}<h2 className="text-xl font-bold">Venue not found</h2></>;
  const venue = venues.value.find((candidate) => candidate.id === selectedId);
  if (!venue) return notFound;

  const [blocks, bookings] = await Promise.all([
    load<VenueBlock[] | null>(listVenueBlocks(venue.id)),
    load<VenueBooking[]>(listApprovedBookings()),
  ]);
  if (!blocks.failed && blocks.value === null) return notFound;
  const venueBookings = bookings.failed ? [] : bookings.value.filter((booking) => booking.venue_id === venue.id);
  const newBlock = blocks.failed ? undefined : (blocks.value ?? []).find((block) => block.id === first(params.block));

  return (
    <>
      {picker}
      {first(params.created) === "1" ? (
        <p role="status" className="mb-6 rounded-xl bg-[#e3f2ea] px-4 py-3 text-sm font-semibold text-[#145c40]">
          {savedMessage(newBlock ? bookingsAffectedBy(newBlock, venueBookings, currentDate()) : [])}
        </p>
      ) : null}
      {venue.status === "blocked" ? (
        <p role="note" className="mb-6 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">
          This venue is blocked in the catalogue, so it is unavailable on every date. Change its availability on the venue&apos;s edit page.
        </p>
      ) : null}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <BlockForm key={venue.id} venues={venues.value.map(({ id, name }) => ({ id, name }))} selectedVenueId={venue.id} />
        <div className="space-y-6">
          {blocks.failed ? (
            // Never fall back to an all-available calendar when blocks are unknown.
            <Alert>Blocks for this venue could not be loaded. Refresh to try again.</Alert>
          ) : bookings.failed ? (
            // The same for approved bookings (SCRUM-15).
            <Alert>Bookings for this venue could not be loaded. Refresh to try again.</Alert>
          ) : (
            <>
              <BlockCalendarTable calendar={buildBlockCalendar(venue, blocks.value ?? [], month, venueBookings)} venueId={venue.id} venueName={venue.name} />
              <BlockList blocks={blocks.value ?? []} />
            </>
          )}
        </div>
      </div>
    </>
  );
}

export default async function VenueBlocksPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireRole("venue_staff");
  const params = await searchParams;
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Venue workspace</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Venue blocks</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Block a venue for maintenance, renovation, safety or internal use. Blocked dates and times are not offered in venue search.</p>
      </div>
      {await VenueBlocksContent({ params })}
    </AppShell>
  );
}
