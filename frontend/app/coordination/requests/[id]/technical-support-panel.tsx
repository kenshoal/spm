import { formatDateTime } from "@/lib/event-requests";
import {
  listCandidates,
  listEventTechnicalSupport,
  listTechnicalSupportStaff,
  skillLabel,
  staffLabel,
  supportsTechnicalSupport,
  type Candidate,
  type StaffOption,
  type TechnicalSupportRequirement,
} from "@/lib/technical-support";
import { AssignStaffForm } from "./assign-staff-form";
import { RequirementForm } from "./requirement-form";

// One requirement: what is needed, who is on it, and how to add someone.
export function TechnicalSupportList({
  requirements,
  staff,
  candidates,
  eventRequestId,
}: {
  requirements: TechnicalSupportRequirement[];
  staff: StaffOption[];
  candidates: ReadonlyMap<string, Candidate[]>;
  eventRequestId: string;
}) {
  if (requirements.length === 0) {
    return (
      <p className="mt-3 text-sm text-[#718078]">No technical support requirements recorded yet.</p>
    );
  }
  return (
    <div className="mt-4 space-y-3">
      {requirements.map((requirement) => {
        const label = skillLabel(requirement.skill_tag);
        const requirementCandidates = candidates.get(requirement.id) ?? [];
        const selectable = requirementCandidates.filter((candidate) => !candidate.already_assigned);
        return (
          <article key={requirement.id} className="rounded-xl border border-[#e1e7e4] p-4">
            <h3 className="font-semibold text-[#1b2b25]">{label} support</h3>
            <p className="mt-1 text-sm text-[#526159]">{requirement.description}</p>
            <p className="mt-1 text-sm text-[#718078]">Recorded by {requirement.recorded_by}</p>
            {requirement.assigned_staff.length === 0 ? (
              <p className="mt-2 text-sm text-[#526159]">Nobody assigned yet</p>
            ) : (
              <ul className="mt-2 space-y-1">
                {requirement.assigned_staff.map((assignment) => (
                  <li key={assignment.staff_id} className="text-sm text-[#526159]">
                    <span className="font-semibold text-[#1b2b25]">
                      {staffLabel(assignment.staff_id, staff)}
                    </span>{" "}
                    · assigned by {assignment.assigned_by} · {formatDateTime(assignment.assigned_at)}
                  </li>
                ))}
              </ul>
            )}
            {requirementCandidates.length === 0 ? (
              <p className="mt-3 text-sm text-[#718078]">
                No suitable Technical Support Staff hold the {label} skill
              </p>
            ) : selectable.length === 0 ? (
              <p className="mt-3 text-sm text-[#718078]">Everyone suitable is already assigned.</p>
            ) : (
              <AssignStaffForm
                eventRequestId={eventRequestId}
                requirementId={requirement.id}
                candidates={requirementCandidates}
                staff={staff}
              />
            )}
          </article>
        );
      })}
    </div>
  );
}

export function TechnicalSupportLoading() {
  return (
    <div
      role="status"
      aria-label="Loading technical support"
      className="mt-5 h-40 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white"
    />
  );
}

// The event's technical support (SCRUM-19 AC4). The API rechecks the caller
// and the status; a failed load is an error, never an empty list.
export async function TechnicalSupportPanel({
  eventRequestId,
  status,
}: {
  eventRequestId: string;
  status: string;
}) {
  if (!supportsTechnicalSupport(status)) return null;
  const [support, staff] = await Promise.all([
    listEventTechnicalSupport(eventRequestId)
      .then((value) => ({ value, failed: false as const }))
      .catch(() => ({ value: [] as TechnicalSupportRequirement[], failed: true as const })),
    listTechnicalSupportStaff(),
  ]);
  const requirements = support.value;
  const candidates = new Map<string, Candidate[]>(
    await Promise.all(
      requirements.map(async (requirement) => {
        return [requirement.id, await listCandidates(eventRequestId, requirement.id)] as const;
      }),
    ),
  );
  return (
    <section aria-label="Technical support" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Technical support</h2>
      {support.failed ? (
        <>
          <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">
            Technical support could not be loaded. Refresh to try again.
          </p>
          <RequirementForm eventRequestId={eventRequestId} />
        </>
      ) : (
        <>
          <TechnicalSupportList
            requirements={requirements}
            staff={staff}
            candidates={candidates}
            eventRequestId={eventRequestId}
          />
          <RequirementForm eventRequestId={eventRequestId} />
        </>
      )}
    </section>
  );
}
