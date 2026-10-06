import type { EventChangeRequest } from "@/lib/event-requests";

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

/** Shows retained proposals while decision and resource-review integration is deferred. */
export function ChangeRequestPanel({ requests }: { requests: EventChangeRequest[] }) {
  if (requests.length === 0) return null;
  return (
    <section aria-labelledby="change-requests-title" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 id="change-requests-title" className="text-lg font-bold text-[#17211d]">Event change requests</h2>
      {requests.some((request) => request.status === "Pending") ? (
        <p role="status" className="mt-3 text-sm text-[#68776f]">You can view proposed changes. Approval and rejection are unavailable until arrangement review is supported. The current event plan remains unchanged.</p>
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
            {request.decision_reason ? <p className="mt-3 text-sm"><strong>Decision reason:</strong> {request.decision_reason}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
