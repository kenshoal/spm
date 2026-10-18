"use client";

import { useActionState } from "react";
import type { SafetyArrangement } from "@/lib/safety";
import { decideSafety, type SafetyDecisionState } from "./actions";

export interface ArrangementOption {
  arrangement: SafetyArrangement;
  id: string;
  label: string;
}

const initialState: SafetyDecisionState = {};
const labelClass = "block text-sm font-semibold text-[#34463f]";

// One form, two submit buttons: the clicked button's value is the decision.
// Approval ignores the reason and targets. Reject is parked (SCRUM-60 AC5).
export function SafetyDecisionForm({
  eventRequestId,
  arrangements,
}: {
  eventRequestId: string;
  arrangements: ArrangementOption[];
}) {
  const [state, formAction, isPending] = useActionState(decideSafety.bind(null, eventRequestId), initialState);
  const errors = state.errors ?? {};
  return (
    <form action={formAction} noValidate className="mt-5 space-y-4 border-t border-[#eef2f0] pt-4">
      <button type="submit" name="decision" value="approved" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        Approve
      </button>
      <label className={labelClass}>What needs to change
        <textarea name="reason" rows={2} defaultValue={state.reason} className="mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832] outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]" />
        {errors.reason ? <span className="mt-1 block text-sm font-normal text-[#a23939]">{errors.reason}</span> : null}
      </label>
      {arrangements.length > 0 ? (
        <fieldset>
          <legend className={labelClass}>Arrangements to recheck</legend>
          <div className="mt-2 space-y-2">
            {arrangements.map((option) => (
              <label key={`${option.arrangement}:${option.id}`} className="flex items-center gap-2 text-sm text-[#273832]">
                <input type="checkbox" name="target" value={`${option.arrangement}:${option.id}`} className="size-4 accent-[#0f6b5b]" />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
      <button type="submit" name="decision" value="changes_requested" disabled={isPending} className="min-h-11 rounded-xl border border-[#80520d] px-5 text-sm font-bold text-[#80520d] hover:bg-[#fff8ec] disabled:opacity-60">
        Ask for changes
      </button>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
