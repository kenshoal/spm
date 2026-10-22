import type { EventChangeRequest, EventRequestStatus } from "@/lib/event-requests";
import { AppliedBookingPlan } from "../../../components/applied-booking-plan";
import { RejectChangeForm } from "./reject-change-form";
import { ApproveChangeForm } from "./approve-change-form";
import { PreviewDateChangeForm } from "./preview-date-change-form";
import { DateChangeApprovalForm } from "./date-change-approval-form";

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
  }).format(new Date(value));
}

const labels: Record<string, string> = {
  proposed_date_times: "Proposed date and time",
  expected_attendance: "Expected attendance",
  venue_requirements: "Venue requirements",
  equipment_requirements: "Equipment requirements",
  registration_needs: "Registration needs",
};

function valueText(key: string, value: unknown): string {
  if (key === "proposed_date_times" && Array.isArray(value)) {
    return value.map((item) => formatDateTime(String(item))).join(", ");
  }
  return String(value);
}

const nonDateFields = new Set(["expected_attendance", "venue_requirements", "equipment_requirements", "registration_needs"]);

function supportsApproval(request: EventChangeRequest): boolean {
  const fields = Object.keys(request.proposed_changes);
  return fields.length > 0 && fields.every((field) => nonDateFields.has(field));
}

/** Retained proposal history with the supported non-date approval and rejection actions. */
export function ChangeRequestPanel({ requests, eventStatus }: {
  requests: EventChangeRequest[];
  eventStatus?: EventRequestStatus;
}) {
  const canDecide = eventStatus === "Approved" || eventStatus === "Planning";
  if (requests.length === 0) return null;
  return (
    <section aria-labelledby="change-requests-title" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 id="change-requests-title" className="text-lg font-bold text-[#17211d]">Event change requests</h2>
      {requests.some((request) => request.status === "Pending") ? (
        <p role="status" className="mt-3 text-sm text-[#68776f]">While the event is Approved or Planning, proposals limited to attendance, venue requirements, equipment requirements and registration requirements can be approved. Affected arrangements will require review; the assigned coordinator acknowledges registration reviews. Date changes require a complete booking plan; all dates and supported mixed fields apply together only if every booking is conflict-free. Rejection requires a reason and leaves the event plan unchanged.</p>
      ) : null}
      <div className="mt-4 space-y-4">
        {requests.map((request) => (
          <article key={request.id} className="rounded-xl border border-[#dce4e0] p-4">
            <div className="flex items-center justify-between gap-3"><strong>{request.status}</strong><span className="text-xs text-[#718078]">{formatDateTime(request.created_at)}</span></div>
            <p className="mt-2 text-sm text-[#526159]">{request.explanation}</p>
            <dl className="mt-3 grid gap-2 text-sm">
              {Object.entries(request.proposed_changes).map(([key, value]) => (
                <div key={key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-3"><dt className="font-semibold text-[#526159]">{labels[key] ?? key}</dt><dd>{valueText(key, value)}</dd></div>
              ))}
            </dl>
            {request.status === "Approved" ? <AppliedBookingPlan plan={request.applied_booking_plan} /> : null}
            {request.decision_reason ? <p className="mt-3 text-sm"><strong>Decision reason:</strong> {request.decision_reason}</p> : null}
            {request.status !== "Pending" && request.coordinator_id ? (
              <p className="mt-2 break-words text-sm"><strong>{request.status} by coordinator:</strong> {request.coordinator_id}</p>
            ) : null}
            {request.status !== "Pending" && request.decided_at ? (
              <p className="mt-1 text-sm"><strong>Decision time:</strong> <time dateTime={request.decided_at}>{formatDateTime(request.decided_at)}</time></p>
            ) : null}
            {canDecide && request.status === "Pending" && supportsApproval(request) ? (
              <ApproveChangeForm eventRequestId={request.event_request_id} changeRequestId={request.id} />
            ) : null}
            {canDecide && request.status === "Pending" && "proposed_date_times" in request.proposed_changes && Object.keys(request.proposed_changes).every((field) => field === "proposed_date_times" || nonDateFields.has(field)) ? (
              <DateChangeApprovalForm eventRequestId={request.event_request_id} changeRequestId={request.id} />
            ) : null}
            {canDecide && request.status === "Pending" && Object.keys(request.proposed_changes).length === 1 && "proposed_date_times" in request.proposed_changes ? (
              <PreviewDateChangeForm eventRequestId={request.event_request_id} changeRequestId={request.id} />
            ) : null}
            {canDecide && request.status === "Pending" ? (
              <RejectChangeForm eventRequestId={request.event_request_id} changeRequestId={request.id} />
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
