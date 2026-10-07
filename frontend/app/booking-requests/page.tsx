import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { BOOKING_STATUSES, type BookingRequestItem, type BookingStatus } from "@/lib/booking-decision-form";
import { listBookingRequests } from "@/lib/booking-requests";
import { listVenues } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../components/app-shell";
import { DecisionForm } from "./decision-form";

const TAB_LABELS: Record<BookingStatus, string> = { pending: "Pending", approved: "Approved", rejected: "Rejected" };
const DECIDED_MESSAGES: Record<string, string> = {
  approved: "Booking approved. The requesting Coordinator has been notified.",
  rejected: "Booking request rejected. The requesting Coordinator has been notified.",
};

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function formatDate(value: string): string {
  return new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function RequestCard({ request, venueName }: { request: BookingRequestItem; venueName: string }) {
  const title = request.event_name ?? "Untitled event";
  return (
    <article aria-labelledby={`booking-${request.id}`} className="rounded-2xl border border-[#dce4e0] bg-white p-5 sm:p-6">
      <h2 id={`booking-${request.id}`} className="text-lg font-bold text-[#1b2b25]">{title}</h2>
      <p className="mt-1 text-sm text-[#273832]">
        {venueName} · {formatDate(request.start_date)} – {formatDate(request.end_date)} · {request.slots.join(", ")}
      </p>
      <p className="mt-1 text-xs text-[#718078]">
        {request.expected_attendance !== null ? `${request.expected_attendance} attendees · ` : ""}
        Requested {formatDate(request.created_at)}
      </p>
      {request.requirements_note ? <p className="mt-2 text-sm text-[#52635c]">Requirements: {request.requirements_note}</p> : null}
      {request.status === "pending" ? (
        <DecisionForm bookingId={request.id} />
      ) : (
        <div className="mt-4 border-t border-[#eef2f0] pt-4 text-sm text-[#273832]">
          <p className="font-semibold">
            {request.status === "approved" ? "Approved" : "Rejected"}
            {request.decided_at ? ` on ${formatDate(request.decided_at)}` : ""}
          </p>
          {request.decision_reason ? <p className="mt-1">Reason: {request.decision_reason}</p> : null}
          {request.suggested_alternative ? <p className="mt-1">Suggested alternative: {request.suggested_alternative}</p> : null}
        </div>
      )}
    </article>
  );
}

async function BookingRequestList({ status }: { status: BookingStatus }) {
  const result = await Promise.all([listBookingRequests(status), listVenues()])
    .then(([requests, venues]) => ({ requests, venues, failed: false as const }))
    .catch((error: unknown) => {
      unstable_rethrow(error);
      return { requests: [], venues: [], failed: true as const };
    });
  if (result.failed) {
    return <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The venue service is unavailable. Start the local API on port 8004, then refresh.</div>;
  }
  if (result.requests.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No {status} booking requests.</p>;
  }
  const names = new Map(result.venues.map((venue) => [venue.id, venue.name]));
  return (
    <div className="space-y-4">
      {result.requests.map((request) => (
        <RequestCard key={request.id} request={request} venueName={names.get(request.venue_id) ?? "Unknown venue"} />
      ))}
    </div>
  );
}

export default async function BookingRequestsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireRole("venue_staff");
  const params = await searchParams;
  const requested = first(params.status);
  const status: BookingStatus = (BOOKING_STATUSES as readonly string[]).includes(requested) ? (requested as BookingStatus) : "pending";
  const decided = DECIDED_MESSAGES[first(params.decided)];
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-6">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Venue workspace</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Booking requests</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Approve a request to book the venue, or reject it with a reason and an optional alternative. Approval is refused if the venue has since been blocked or booked.</p>
      </div>
      <nav aria-label="Booking request status" className="mb-6 flex gap-2">
        {BOOKING_STATUSES.map((tab) => (
          <Link
            key={tab}
            href={`/booking-requests?status=${tab}`}
            aria-current={tab === status ? "page" : undefined}
            className={`rounded-full px-4 py-2 text-sm font-semibold ${tab === status ? "bg-[#0f6b5b] text-white" : "border border-[#cfd9d4] text-[#273832] hover:bg-[#e3f2ea]"}`}
          >
            {TAB_LABELS[tab]}
          </Link>
        ))}
      </nav>
      {decided ? <p role="status" className="mb-6 rounded-xl bg-[#e3f2ea] px-4 py-3 text-sm font-semibold text-[#145c40]">{decided}</p> : null}
      {await BookingRequestList({ status })}
    </AppShell>
  );
}
