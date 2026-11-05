import { unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { formatBookingDates, listEventBookings, type EventBooking } from "@/lib/event-bookings";
import type { EventRequest } from "@/lib/event-requests";
import {
  listEventRequirements,
  listEventReservations,
  listSafetyQueue,
  overlappingBlocks,
  type EquipmentRequirement,
  type EquipmentReservation,
} from "@/lib/safety";
import { reasonLabel, type VenueBlock } from "@/lib/venue-block-options";
import { listVenueBlocks } from "@/lib/venue-blocks";
import { getVenue, layoutLabel, type Venue } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../components/app-shell";
import { SafetyDecisionForm, type ArrangementOption } from "./decision-form";
import { timeRangeLabel } from "@/lib/venue-options";

const DECIDED_MESSAGES: Record<string, string> = {
  approved: "Event approved. It is now Confirmed.",
  changes_requested: "Changes requested. The event is back in Planning and its coordinator has been notified.",
  rejected: "Safety arrangement rejected. The event is back in Planning and its coordinator has been notified.",
};

interface BookingCheck {
  booking: EventBooking;
  venue: Venue | null;
  // null when the venue's blocks could not be loaded: unknown, not "none".
  restrictions: VenueBlock[] | null;
}

const NOT_LOADED =
  "Venue details or restrictions couldn't be loaded. Don't approve until this is fixed.";

interface SafetyCheck {
  event: EventRequest;
  bookings: BookingCheck[];
  requirements: EquipmentRequirement[];
  reservations: EquipmentReservation[];
}

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

// Everything the officer needs for one event, from the three services that own it.
async function loadCheck(event: EventRequest): Promise<SafetyCheck> {
  const [bookings, requirements, reservations] = await Promise.all([
    listEventBookings(event.id),
    listEventRequirements(event.id),
    listEventReservations(event.id),
  ]);
  const live = bookings.filter((booking) => booking.status !== "cancelled" && booking.status !== "rejected");
  const checks = await Promise.all(
    live.map(async (booking) => {
      const [venue, blocks] = await Promise.all([getVenue(booking.venue_id), listVenueBlocks(booking.venue_id)]);
      return { booking, venue, restrictions: blocks === null ? null : overlappingBlocks(blocks, booking) };
    }),
  );
  return { event, bookings: checks, requirements, reservations };
}

function arrangementOptions(check: SafetyCheck): ArrangementOption[] {
  return [
    ...check.bookings.map(({ booking, venue }) => ({
      arrangement: "venue_booking" as const,
      id: booking.id,
      label: `${venue?.name ?? "Unknown venue"}, ${formatBookingDates(booking.start_date, booking.end_date)}`,
    })),
    ...check.reservations.map((reservation) => {
      const requirement = check.requirements.find((item) => item.id === reservation.requirement_id);
      return {
        arrangement: "equipment_reservation" as const,
        id: reservation.id,
        label: `${reservation.quantity} × ${requirement?.equipment_type ?? "Equipment"}`,
      };
    }),
  ];
}

function CheckCard({ check }: { check: SafetyCheck }) {
  const { event } = check;
  return (
    <article aria-labelledby={`safety-${event.id}`} className="rounded-2xl border border-[#dce4e0] bg-white p-5 sm:p-6">
      <h2 id={`safety-${event.id}`} className="text-lg font-bold text-[#1b2b25]">{event.event_name ?? "Untitled event"}</h2>
      <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        <div><dt className="font-semibold text-[#34463f]">Expected attendance</dt><dd className="text-[#273832]">{event.expected_attendance ?? "Not given"}</dd></div>
        <div><dt className="font-semibold text-[#34463f]">Accessibility needs</dt><dd className="text-[#273832]">{event.accessibility_needs ?? "None given"}</dd></div>
      </dl>

      <h3 className="mt-5 text-sm font-bold uppercase tracking-[0.08em] text-[#52635c]">Venues</h3>
      {check.bookings.length === 0 ? (
        <p className="mt-2 text-sm text-[#718078]">No active venue bookings.</p>
      ) : (
        <ul className="mt-2 space-y-3">
          {check.bookings.map(({ booking, venue, restrictions }) => (
            <li key={booking.id} className="rounded-xl border border-[#eef2f0] p-3 text-sm text-[#273832]">
              <p className="font-semibold">{venue?.name ?? "Unknown venue"} · {formatBookingDates(booking.start_date, booking.end_date)} · {timeRangeLabel(booking.start_minute, booking.end_minute)}</p>
              {venue ? (
                <p className="mt-1">
                  Capacity {venue.max_capacity}
                  {event.expected_attendance !== null && event.expected_attendance > venue.max_capacity ? " (below expected attendance)" : ""}
                  {" · "}Layouts: {venue.supported_layouts.map(layoutLabel).join(", ") || "none"}
                  {" · "}Accessibility: {venue.accessibility_features.join(", ") || "none recorded"}
                </p>
              ) : null}
              {venue === null || restrictions === null ? (
                <p className="mt-1 font-semibold text-[#8e3d35]">{NOT_LOADED}</p>
              ) : restrictions.length > 0 ? (
                <ul className="mt-1 text-[#8e3d35]">
                  {restrictions.map((block) => (
                    <li key={block.id}>Restriction: {reasonLabel(block.reason_category)}{block.reason_detail ? ` (${block.reason_detail})` : ""}, {formatBookingDates(block.start_date, block.end_date)} · {timeRangeLabel(block.start_minute, block.end_minute)}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[#718078]">No venue restrictions on these dates.</p>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3 className="mt-5 text-sm font-bold uppercase tracking-[0.08em] text-[#52635c]">Equipment</h3>
      {check.requirements.length === 0 ? (
        <p className="mt-2 text-sm text-[#718078]">No equipment requirements.</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm text-[#273832]">
          {check.requirements.map((requirement) => {
            const reserved = check.reservations
              .filter((reservation) => reservation.requirement_id === requirement.id)
              .reduce((total, reservation) => total + reservation.quantity, 0);
            return (
              <li key={requirement.id}>
                {requirement.quantity} × {requirement.equipment_type} · {reserved} reserved
                {requirement.technical_requirements ? ` · ${requirement.technical_requirements}` : ""}
              </li>
            );
          })}
        </ul>
      )}

      <SafetyDecisionForm
        eventRequestId={event.id}
        arrangements={arrangementOptions(check)}
        approveBlockedReason={
          check.bookings.some(({ venue, restrictions }) => venue === null || restrictions === null) ? NOT_LOADED : undefined
        }
      />
    </article>
  );
}

async function SafetyQueue() {
  const result = await listSafetyQueue()
    .then((events) => Promise.all(events.map(loadCheck)))
    .then((checks) => ({ checks, failed: false as const }))
    .catch((error: unknown) => {
      unstable_rethrow(error);
      return { checks: [], failed: true as const };
    });
  if (result.failed) {
    return <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The safety queue could not be loaded. Check that the event, venue and equipment services are running, then refresh.</div>;
  }
  if (result.checks.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No events are waiting for a safety check.</p>;
  }
  return (
    <div className="space-y-4">
      {result.checks.map((check) => <CheckCard key={check.event.id} check={check} />)}
    </div>
  );
}

export default async function SafetyPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireRole("safety_officer");
  const decided = DECIDED_MESSAGES[first((await searchParams).decided)];
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-6">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Safety workspace</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Safety checks</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Events whose venues and equipment are booked, longest-waiting first. Approve to confirm the event, or ask for changes and tick the arrangements to recheck.</p>
      </div>
      {decided ? <p role="status" className="mb-5 rounded-xl border border-[#cfe5da] bg-[#eef8f3] px-4 py-3 text-sm text-[#145c40]">{decided}</p> : null}
      <SafetyQueue />
    </AppShell>
  );
}
