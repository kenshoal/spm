import Link from "next/link";
import { notFound, unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { getOpenEvent, isFull, isRegistrationOpen, isWaitlistOpen, listMyRegistrations, listMyWaitlist, type PublicEvent } from "@/lib/attendee";
import { formatBookingDates } from "@/lib/booking-dates";
import { formatDateTime } from "@/lib/event-requests";
import { timeRangeLabel } from "@/lib/venue-options";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { ActionButton } from "../action-button";
import { joinWaitlist, registerForEvent } from "../actions";

export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole("attendee");
  const { id } = await params;
  let event: PublicEvent | null = null;
  try {
    event = await getOpenEvent(id);
  } catch (error) {
    unstable_rethrow(error);
    return (
      <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
        <p role="alert" className="rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">This event could not be loaded. Refresh to try again.</p>
      </AppShell>
    );
  }
  if (event === null) notFound();
  const [registrations, waitlist] = await Promise.all([
    listMyRegistrations().catch(() => []),
    listMyWaitlist().catch(() => []),
  ]);
  const registered = registrations.some((row) => row.event_request_id === id && row.status === "Registered");
  const waiting = waitlist.some((row) => row.event_request_id === id && row.status !== "Closed");
  const open = isRegistrationOpen(event);
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-3xl">
        <Link href="/events" className="mb-5 inline-flex text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to events</Link>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d]">{event.event_name ?? "Event"}</h1>
        <dl className="mt-6 grid gap-4 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:grid-cols-2">
          <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">When</dt><dd>{event.proposed_date_times.map(formatDateTime).join(", ")}</dd></div>
          <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Where</dt>
            <dd>{event.venues.length === 0 ? "To be confirmed" : event.venues.map((venue, index) => (
              <span key={index} className="block">{venue.name}, {venue.location} · {formatBookingDates(venue.start_date, venue.end_date)}, {timeRangeLabel(venue.start_minute, venue.end_minute)}</span>
            ))}</dd></div>
          {event.purpose ? <div className="sm:col-span-2"><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">About</dt><dd>{event.purpose}</dd></div> : null}
          {event.description ? <div className="sm:col-span-2"><dd className="text-sm text-[#526159]">{event.description}</dd></div> : null}
          <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Registration</dt>
            <dd>{event.registration_opens_at && event.registration_closes_at ? `${formatDateTime(event.registration_opens_at)} to ${formatDateTime(event.registration_closes_at)}` : "Not set"}</dd></div>
          <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Places left</dt><dd>{event.places_remaining ?? "Not limited"}</dd></div>
        </dl>
        <div className="mt-6">
          {registered ? (
            <p role="status" className="rounded-xl bg-[#e7f4ee] px-4 py-3 text-sm font-semibold text-[#145c40]">You are registered for this event. Manage it from your events page.</p>
          ) : waiting ? (
            <p role="status" className="rounded-xl bg-[#fff9eb] px-4 py-3 text-sm font-semibold text-[#6f4b12]">You are on the waiting list for this event.</p>
          ) : !open ? (
            <p role="status" className="text-sm text-[#718078]">Registration is not open right now.</p>
          ) : isFull(event) && !isWaitlistOpen(event) ? (
            <p role="status" className="text-sm text-[#718078]">This event is full and its waiting list has closed.</p>
          ) : isFull(event) ? (
            <ActionButton label="Join the waiting list" pendingLabel="Joining…" run={joinWaitlist.bind(null, id)} />
          ) : (
            <ActionButton label="Register" pendingLabel="Registering…" run={registerForEvent.bind(null, id)} />
          )}
        </div>
      </div>
    </AppShell>
  );
}
