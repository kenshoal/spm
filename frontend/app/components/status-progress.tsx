import type { EventRequestStatus } from "@/lib/event-requests";

// Milestones an organiser can expect after submission. "Changes Requested"
// isn't a milestone — it rewinds the flow to just after Under Review.
const MILESTONES = [
  "Submitted",
  "Under Review",
  "Approved",
  "Planning",
  "Confirmed",
  "Completed",
] as const;

const STATUS_DESCRIPTIONS: Record<EventRequestStatus, string> = {
  Draft: "Not submitted yet — you can keep editing this draft.",
  Submitted: "Waiting for an Event Operations Manager to assign a coordinator.",
  "Under Review": "A coordinator is reviewing this request.",
  "Changes Requested":
    "The coordinator requested changes. Update the request and resubmit it.",
  Approved: "Approved — the event can move into planning.",
  Planning: "Venues and equipment are being arranged.",
  Confirmed: "Confirmed — the event is set to go ahead.",
  Completed: "This event has finished.",
  Cancelled: "This request has been cancelled.",
  Rejected: "This request was rejected after review.",
};

const BADGE_STYLES: Partial<Record<EventRequestStatus, string>> = {
  Draft: "bg-[#eef4f1] text-[#315047]",
  Cancelled: "bg-[#fdecea] text-[#8c3a2b]",
  Rejected: "bg-[#fdecea] text-[#8c3a2b]",
  Completed: "bg-[#e3f2ea] text-[#145c40]",
};

function badgeStyle(status: EventRequestStatus): string {
  return (
    BADGE_STYLES[status] ?? "bg-[#fff3dc] text-[#80520d]"
  );
}

export function StatusProgress({ status }: { status: EventRequestStatus }) {
  const description = STATUS_DESCRIPTIONS[status];

  // Cancelled and Rejected get no stepper: later stages are unreachable and
  // showing them would imply the event could still proceed.
  const reachedIndex =
    status === "Changes Requested"
      ? MILESTONES.indexOf("Under Review")
      : MILESTONES.indexOf(status as (typeof MILESTONES)[number]);
  const milestones = MILESTONES.slice(0, reachedIndex + 1);

  return (
    <section aria-label="Status progress" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${badgeStyle(status)}`}>
          {status}
        </span>
        <p className="text-sm leading-6 text-[#68776f]">{description}</p>
      </div>

      {status === "Changes Requested" ? (
        <div role="status" className="mt-5 rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">
          The coordinator requested changes. The organiser needs to update and resubmit this request before coordination can continue.
        </div>
      ) : null}
      {status === "Cancelled" ? (
        <div role="status" className="mt-5 rounded-xl border border-[#f2cfca] bg-[#fdf3f1] px-4 py-3 text-sm text-[#8c3a2b]">
          This request was cancelled by the coordinator. No further stages will follow.
        </div>
      ) : null}
      {status === "Rejected" ? (
        <div role="status" className="mt-5 rounded-xl border border-[#f2cfca] bg-[#fdf3f1] px-4 py-3 text-sm text-[#8c3a2b]">
          This request was rejected. No further stages will follow.
        </div>
      ) : null}

      {milestones.length > 0 ? (
        <ol className="mt-6 flex flex-wrap gap-x-7 gap-y-3">
          {milestones.map((milestone, index) => {
            const state =
              index < reachedIndex ? "done" : index === reachedIndex ? "current" : "upcoming";
            return (
              <li
                key={milestone}
                aria-current={state === "current" ? "step" : undefined}
                className="flex items-center gap-2"
              >
                <span
                  aria-hidden="true"
                  className={`inline-block size-2.5 rounded-full ${state === "done" ? "bg-[#0f6b5b]" : state === "current" ? "bg-[#0f6b5b] ring-2 ring-[#0f6b5b] ring-offset-2" : "bg-[#cbd7d1]"}`}
                />
                <span className="sr-only">
                  {state === "done"
                    ? "Completed stage: "
                    : state === "current"
                      ? "Current stage: "
                      : "Not started: "}
                </span>
                <span className={`text-sm ${state === "current" ? "font-bold text-[#0f6b5b]" : state === "done" ? "text-[#273832]" : "text-[#718078]"}`}>
                  {milestone}
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
