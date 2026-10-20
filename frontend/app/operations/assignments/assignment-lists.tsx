import { formatDateTime, statusBadgeClass, type EventRequest } from "@/lib/event-requests";
import { coordinatorLabel, groupByCoordinator, type CoordinatorOption, type CurrentAssignment } from "@/lib/operations";
import { CalendarIcon, PeopleIcon } from "../../components/icons";
import { AssignCoordinatorForm } from "./assign-coordinator-form";

function RequestSummary({ request, headingLevel: Heading = "h3" }: { request: EventRequest; headingLevel?: "h3" | "h4" }) {
  const headingId = `request-${request.id}`;
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <Heading id={headingId} className="text-base font-bold text-[#1b2b25] sm:text-lg">{request.event_name ?? "Untitled event request"}</Heading>
        <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${statusBadgeClass(request.status)}`}>{request.status}</span>
      </div>
      <p className="mt-2 line-clamp-2 text-sm text-[#68776f]">{request.purpose ?? "Purpose not provided"}</p>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-[#718078]">
        <span className="inline-flex items-center gap-1.5"><CalendarIcon className="size-4" />{request.proposed_date_times[0] ? formatDateTime(request.proposed_date_times[0]) : "Date not set"}</span>
        <span className="inline-flex items-center gap-1.5"><PeopleIcon className="size-4" />{request.expected_attendance ? `${request.expected_attendance} attendees` : "Attendance not set"}</span>
      </div>
    </>
  );
}

const cardClass = "rounded-2xl border border-[#dce4e0] bg-white p-5 sm:p-6";

export function AwaitingList({ requests, coordinators }: { requests: EventRequest[]; coordinators: CoordinatorOption[] }) {
  if (requests.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-10 text-center text-sm text-[#718078]">Nothing is waiting for a coordinator.</p>;
  }
  return (
    <div className="space-y-3">
      {requests.map((request) => (
        <article key={request.id} aria-labelledby={`request-${request.id}`} className={cardClass}>
          <RequestSummary request={request} />
          <div className="mt-4 border-t border-[#edf1ef] pt-4">
            <AssignCoordinatorForm eventRequestId={request.id} coordinators={coordinators} />
          </div>
        </article>
      ))}
    </div>
  );
}

// One group per coordinator, including those with nothing active (SCRUM-62 AC3).
export function AssignedList({ assignments, coordinators }: { assignments: CurrentAssignment[]; coordinators: CoordinatorOption[] }) {
  const groups = groupByCoordinator(assignments, coordinators);
  if (groups.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-10 text-center text-sm text-[#718078]">No in-progress request has a coordinator yet.</p>;
  }
  return (
    <div className="space-y-8">
      {groups.map((group) => {
        const headingId = `coordinator-${group.coordinatorId}`;
        return (
          <section key={group.coordinatorId} aria-labelledby={headingId}>
            <h3 id={headingId} className="mb-3 text-base font-bold text-[#1b2b25]">
              {group.label} ({group.assignments.length})
            </h3>
            {group.assignments.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-5 text-sm text-[#718078]">No active events</p>
            ) : (
              <div className="space-y-3">
                {group.assignments.map(({ event_request: request, assignment }) => (
                  <article key={request.id} aria-labelledby={`request-${request.id}`} className={cardClass}>
                    <RequestSummary request={request} headingLevel="h4" />
                    <p className="mt-3 text-sm text-[#273832]">
                      Coordinator: <span className="font-semibold">{coordinatorLabel(assignment.coordinator_id, coordinators)}</span>
                      <span className="text-[#718078]"> · assigned {formatDateTime(assignment.assigned_at)}</span>
                    </p>
                    <div className="mt-4 border-t border-[#edf1ef] pt-4">
                      <AssignCoordinatorForm eventRequestId={request.id} coordinators={coordinators} currentCoordinatorId={assignment.coordinator_id} />
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
