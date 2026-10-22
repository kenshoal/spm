"use client";

import { useActionState } from "react";
import {
  staffLabel,
  type Candidate,
  type StaffOption,
} from "@/lib/technical-support-options";
import {
  assignSupportStaff,
  type TechnicalSupportActionState,
} from "./technical-support-actions";

const initialState: TechnicalSupportActionState = {};

// One assignment per submit. The select offers only staff not already on the
// requirement; the API rechecks suitability and repeats (AC2).
export function AssignStaffForm({
  eventRequestId,
  requirementId,
  candidates,
  staff,
}: {
  eventRequestId: string;
  requirementId: string;
  candidates: Candidate[];
  staff: StaffOption[];
}) {
  const [state, formAction, isPending] = useActionState(assignSupportStaff, initialState);
  const selectable = candidates.filter((candidate) => !candidate.already_assigned);
  return (
    <form action={formAction} className="mt-3 flex flex-wrap items-center gap-2">
      <input type="hidden" name="event_request_id" value={eventRequestId} />
      <input type="hidden" name="requirement_id" value={requirementId} />
      <label htmlFor={`assign-${requirementId}`} className="sr-only">
        Technical Support Staff
      </label>
      <select
        id={`assign-${requirementId}`}
        name="staff_id"
        disabled={isPending}
        className="min-h-11 rounded-lg border border-[#cfd9d4] bg-white px-3 text-sm text-[#1b2b25]"
      >
        {selectable.map((candidate) => (
          <option key={candidate.staff_id} value={candidate.staff_id}>
            {staffLabel(candidate.staff_id, staff)}
          </option>
        ))}
      </select>
      <button
        type="submit"
        disabled={isPending || selectable.length === 0}
        className="min-h-9 rounded-lg bg-[#0f6b5b] px-3 text-sm font-semibold text-white hover:bg-[#0c584b] disabled:opacity-60"
      >
        {isPending ? "Assigning…" : "Assign"}
      </button>
      {state.message ? (
        <p role="alert" className="w-full text-sm text-[#a23939]">
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
