"use client";

import { useActionState } from "react";
import { decideBookingRequest, type DecisionFormState } from "./actions";

const initialState: DecisionFormState = {};
const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832] outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

// One form, two submit buttons: the clicked button's value is the decision.
// Approval ignores the rejection fields (SCRUM-15 AC2).
export function DecisionForm({ bookingId }: { bookingId: string }) {
  const [state, formAction, isPending] = useActionState(decideBookingRequest.bind(null, bookingId), initialState);
  const errors = state.errors ?? {};
  return (
    <form action={formAction} noValidate className="mt-4 space-y-4 border-t border-[#eef2f0] pt-4">
      <button type="submit" name="decision" value="approved" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        Approve
      </button>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>Reason for rejecting
          <textarea name="reason" rows={2} defaultValue={state.values?.reason} className={inputClass} />
          {errors.reason ? <span className="mt-1 block text-sm font-normal text-[#a23939]">{errors.reason}</span> : null}
        </label>
        <label className={labelClass}>Suggested alternative (optional)
          <textarea name="suggested_alternative" rows={2} defaultValue={state.values?.suggested_alternative} placeholder="Another venue, date or arrangement" className={inputClass} />
        </label>
      </div>
      <button type="submit" name="decision" value="rejected" disabled={isPending} className="min-h-11 rounded-xl border border-[#a23939] px-5 text-sm font-bold text-[#a23939] hover:bg-[#fff4f3] disabled:opacity-60">
        Reject
      </button>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
