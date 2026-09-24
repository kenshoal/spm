"use client";

import { useActionState } from "react";
import { assignCoordinator, type AssignState } from "../actions";
import type { CoordinatorOption } from "@/lib/operations";

const initialState: AssignState = {};

export function AssignCoordinatorForm({
  eventRequestId,
  coordinators,
  currentCoordinatorId,
}: {
  eventRequestId: string;
  coordinators: CoordinatorOption[];
  currentCoordinatorId?: string;
}) {
  const [state, formAction, isPending] = useActionState(
    assignCoordinator.bind(null, eventRequestId),
    initialState,
  );
  const choices = coordinators.filter((coordinator) => coordinator.id !== currentCoordinatorId);

  if (choices.length === 0) {
    return (
      <p className="text-sm text-[#718078]">
        {currentCoordinatorId ? "No other Event Coordinator is available." : "No Event Coordinator is available to assign."}
      </p>
    );
  }

  return (
    <form action={formAction} className="flex flex-wrap items-end gap-3">
      <label className="text-sm font-semibold text-[#34463f]">
        Coordinator
        <select
          name="coordinator_id"
          defaultValue=""
          className="mt-1 block min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm text-[#273832]"
        >
          <option value="">Choose a coordinator</option>
          {choices.map((coordinator) => (
            <option key={coordinator.id} value={coordinator.id}>
              {coordinator.email ?? coordinator.id}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={isPending}
        className="min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-semibold text-white hover:bg-[#0b5b4d] disabled:opacity-60"
      >
        {isPending ? "Saving…" : currentCoordinatorId ? "Reassign" : "Assign"}
      </button>
      {state.message ? (
        <p role={state.assigned ? "status" : "alert"} className={`w-full rounded-lg px-3 py-2 text-sm ${state.assigned ? "bg-[#e7f5ed] text-[#145d40]" : "bg-[#fff0f0] text-[#a23939]"}`}>
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
