import type { EventChangeRequest } from "@/lib/event-requests";
import { AppliedBookingPlan } from "./applied-booking-plan";
import { RefusedChanges } from "./refused-changes";
import { formatDateTime } from "@/lib/event-requests";

const labels: Record<string, string> = {
  proposed_date_times: "Proposed date and time",
  expected_attendance: "Expected attendance",
  venue_requirements: "Venue requirements",
  equipment_requirements: "Equipment requirements",
  registration_needs: "Registration needs",
};

export function ChangeRequestHistory({ requests }: { requests: EventChangeRequest[] }) {
  if (requests.length === 0) return null;
  return (
    <section aria-labelledby="organiser-change-history" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 id="organiser-change-history" className="text-lg font-bold text-[#17211d]">Change request history</h2>
      <div className="mt-4 space-y-4">
        {requests.map((request) => (
          <article key={request.id} className="rounded-xl border border-[#dce4e0] p-4">
            <div className="flex justify-between gap-3"><strong>{request.status}</strong><span className="text-xs text-[#718078]">{formatDateTime(request.created_at)}</span></div>
            <p className="mt-2 text-sm text-[#526159]">{request.explanation}</p>
            <ul className="mt-3 space-y-1 text-sm">
              {Object.entries(request.proposed_changes).map(([key, value]) => <li key={key}><strong>{labels[key] ?? key}:</strong> {Array.isArray(value) ? value.map(String).join(", ") : String(value)}</li>)}
            </ul>
            {request.status === "Approved" || request.status === "Partially Approved" ? <AppliedBookingPlan plan={request.applied_booking_plan} /> : null}
            <RefusedChanges request={request} />
            {request.decision_reason ? <p className="mt-3 text-sm"><strong>Coordinator reason:</strong> {request.decision_reason}</p> : null}
            {request.status !== "Pending" && request.coordinator_id ? (
              <p className="mt-2 break-words text-sm"><strong>{request.status} by coordinator:</strong> {request.coordinator_id}</p>
            ) : null}
            {request.status !== "Pending" && request.decided_at ? (
              <p className="mt-1 text-sm"><strong>Decision time:</strong> <time dateTime={request.decided_at}>{formatDateTime(request.decided_at)}</time></p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
