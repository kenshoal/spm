import { statusBadgeClass, type EventRequestStatus } from "@/lib/event-requests";

const MILESTONES = [
  "Draft",
  "Submitted",
  "Under Review",
  "Approved",
  "Planning",
  "Confirmed",
  "Completed",
] as const;

type Milestone = (typeof MILESTONES)[number];
type MilestoneState = "done" | "current" | "upcoming";

const STATUS_DESCRIPTIONS: Record<EventRequestStatus, string> = {
  Draft: "Not submitted yet — you can keep editing this draft.",
  Submitted: "Submitted for coordination.",
  "Under Review": "A coordinator is reviewing this request.",
  "Changes Requested": "The coordinator needs clarification before review can continue.",
  Approved: "Approved — the event can move into planning.",
  Planning: "Venues and equipment are being arranged.",
  Confirmed: "Confirmed — the event is set to go ahead.",
  Completed: "This event has finished and reached the final stage.",
  Cancelled: "This request has been cancelled.",
  Rejected: "This request was rejected after review.",
};

function milestoneState(status: EventRequestStatus, milestone: Milestone): MilestoneState {
  if (status === "Rejected") {
    return MILESTONES.indexOf(milestone) <= MILESTONES.indexOf("Under Review")
      ? "done"
      : "upcoming";
  }
  if (status === "Cancelled") {
    return milestone === "Draft" || milestone === "Submitted" ? "done" : "upcoming";
  }
  const reachedStatus = status === "Changes Requested" ? "Under Review" : status;
  const reachedIndex = MILESTONES.indexOf(reachedStatus as Milestone);
  const index = MILESTONES.indexOf(milestone);
  if (index < reachedIndex) return "done";
  if (index === reachedIndex) return "current";
  return "upcoming";
}

export function StatusProgress({
  status,
  coordinatorAssigned,
}: {
  status: EventRequestStatus;
  coordinatorAssigned?: boolean;
}) {
  const description =
    status === "Submitted"
      ? coordinatorAssigned === true
        ? "A coordinator has been assigned and can begin review."
        : coordinatorAssigned === false
          ? "Waiting for an Event Operations Manager to assign a coordinator."
          : STATUS_DESCRIPTIONS.Submitted
      : STATUS_DESCRIPTIONS[status];

  return (
    <section aria-label="Status progress" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${statusBadgeClass(status)}`}>
          {status}
        </span>
        <p className="text-sm leading-6 text-[#68776f]">{description}</p>
      </div>

      {status === "Changes Requested" ? (
        <div role="status" className="mt-5 rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">
          A clarification response is required before review can continue. The submitted request remains read-only.
        </div>
      ) : null}
      {status === "Cancelled" || status === "Rejected" ? (
        <div role="status" className="mt-5 rounded-xl border border-[#f2cfca] bg-[#fdf3f1] px-4 py-3 text-sm text-[#8c3a2b]">
          This request ended as {status.toLowerCase()}; the later stages shown below were not reached.
        </div>
      ) : null}

      <div className="mt-6 overflow-x-auto pb-2">
        <ol aria-label="Full event journey" className="flex min-w-[56rem] items-stretch">
          {MILESTONES.map((milestone, index) => {
            const state = milestoneState(status, milestone);
            const shape =
              index === 0
                ? "polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%)"
                : "polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%, 14px 50%)";
            return (
              <li
                key={milestone}
                aria-current={state === "current" ? "step" : undefined}
                style={{ clipPath: shape }}
                className={`relative flex min-h-12 flex-1 items-center justify-center px-5 py-3 text-center first:pl-4 ${index > 0 ? "-ml-px" : ""} ${state === "current" ? "z-10 bg-[#0f6b5b] text-white shadow-sm" : state === "done" ? "bg-[#dcebe5] text-[#174f42]" : "bg-[#edf1ef] text-[#68776f]"}`}
              >
                <span className="sr-only">
                  {state === "done" ? "Completed stage: " : state === "current" ? "Current stage: " : "Not reached yet: "}
                </span>
                <span className="whitespace-nowrap text-xs font-bold sm:text-sm">{milestone}</span>
                {state === "done" ? <span aria-hidden="true" className="ml-1.5 text-sm">✓</span> : null}
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
