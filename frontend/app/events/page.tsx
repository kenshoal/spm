import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import {
  listMyRegistrations,
  listMyWaitlist,
  listOpenEvents,
  type MyRegistration,
  type MyWaitlistEntry,
  type PublicEvent,
} from "@/lib/attendee";
import { formatDateTime } from "@/lib/event-requests";
import { AppShell, workspaceLinks } from "../components/app-shell";
import { ActionButton } from "./action-button";
import { acceptWaitlistOffer, withdrawFromWaitlist, withdrawRegistration } from "./actions";

async function load<T>(read: () => Promise<T>, empty: T): Promise<{ value: T; failed: boolean }> {
  try {
    return { value: await read(), failed: false };
  } catch (error) {
    unstable_rethrow(error);
    return { value: empty, failed: true };
  }
}

const Failed = ({ what }: { what: string }) => (
  <p role="alert" className="rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">{what} could not be loaded. Refresh to try again.</p>
);

export default async function EventsPage() {
  const user = await requireRole("attendee");
  const [events, registrations, waitlist] = await Promise.all([
    load<PublicEvent[]>(listOpenEvents, []),
    load<MyRegistration[]>(listMyRegistrations, []),
    load<MyWaitlistEntry[]>(listMyWaitlist, []),
  ]);
  const registered = registrations.value.filter((row) => row.status === "Registered");
  const names = new Map(registrations.value.map((row) => [row.event_request_id, row.event.event_name]));
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Attendee</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Events</h1>
      </div>

      <section aria-label="My registrations" className="mb-10">
        <h2 className="mb-3 text-xl font-bold text-[#17211d]">My registrations</h2>
        {registrations.failed ? <Failed what="Your registrations" /> : registered.length === 0 ? (
          <p className="text-sm text-[#718078]">You have not registered for any event.</p>
        ) : (
          <ul className="space-y-3">
            {registered.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#dce4e0] bg-white p-5">
                <div>
                  <Link href={`/events/${row.event_request_id}`} className="font-bold text-[#17211d] hover:underline">{row.event.event_name ?? "Event"}</Link>
                  <p className="text-sm text-[#68776f]">{row.attended_at ? "Checked in" : "Registered"} · {row.event.proposed_date_times.map(formatDateTime).join(", ")}</p>
                </div>
                {row.attended_at ? null : (
                  <ActionButton label="Withdraw" pendingLabel="Withdrawing…" tone="quiet" run={withdrawRegistration.bind(null, row.id)} />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="My waiting list" className="mb-10">
        <h2 className="mb-3 text-xl font-bold text-[#17211d]">Waiting list</h2>
        {waitlist.failed ? <Failed what="Your waiting list" /> : waitlist.value.filter((row) => row.status !== "Closed").length === 0 ? (
          <p className="text-sm text-[#718078]">You are not on any waiting list.</p>
        ) : (
          <ul className="space-y-3">
            {waitlist.value.filter((row) => row.status !== "Closed").map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#dce4e0] bg-white p-5">
                <div>
                  <Link href={`/events/${row.event_request_id}`} className="font-bold text-[#17211d] hover:underline">{row.event_name ?? names.get(row.event_request_id) ?? "Event"}</Link>
                  <p className="text-sm text-[#68776f]">
                    {row.status === "Offered" && row.expires_at
                      ? `A place is yours until ${formatDateTime(row.expires_at)}. Accept it before then.`
                      : `Position ${row.position ?? "—"} in the queue`}
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  {row.status === "Offered" ? <ActionButton label="Accept the place" pendingLabel="Accepting…" run={acceptWaitlistOffer.bind(null, row.id)} /> : null}
                  <ActionButton label="Leave the list" pendingLabel="Leaving…" tone="quiet" run={withdrawFromWaitlist.bind(null, row.id)} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Open events">
        <h2 className="mb-3 text-xl font-bold text-[#17211d]">Open for registration</h2>
        {events.failed ? <Failed what="Events" /> : events.value.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No event is open for registration right now.</p>
        ) : (
          <ul className="space-y-3">
            {events.value.map((event) => (
              <li key={event.id}>
                <Link href={`/events/${event.id}`} className="block rounded-2xl border border-[#dce4e0] bg-white p-5 hover:border-[#0f6b5b]">
                  <p className="font-bold text-[#17211d]">{event.event_name ?? "Event"}</p>
                  <p className="mt-1 text-sm text-[#68776f]">
                    {event.proposed_date_times.map(formatDateTime).join(", ")}
                    {event.venues[0] ? ` · ${event.venues[0].name}` : ""}
                    {event.places_remaining === null ? "" : event.places_remaining > 0 ? ` · ${event.places_remaining} places left` : " · Full"}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </AppShell>
  );
}
