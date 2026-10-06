"use client";

import { useActionState } from "react";
import { createEventChangeRequest } from "../actions";

export function ChangeRequestForm({ eventRequestId }: { eventRequestId: string }) {
  const action = createEventChangeRequest.bind(null, eventRequestId);
  const [state, formAction, pending] = useActionState(action, {});
  if (state.submitted) {
    return <div role="status" className="rounded-xl border border-[#bcd9ce] bg-[#edf7f3] px-4 py-3 text-sm text-[#145c40]">Your change request was sent to the assigned coordinator.</div>;
  }
  return (
    <section aria-labelledby="request-change-title" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 id="request-change-title" className="pr-16 text-lg font-bold text-[#17211d]">Request a change</h2>
      <p className="mt-2 text-sm leading-6 text-[#68776f]">Only complete the event details that should change. The current plan stays active until your coordinator approves.</p>
      <form action={formAction} className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="sm:col-span-2 text-sm font-semibold text-[#34463f]">Reason for change
          <textarea name="explanation" required maxLength={2000} rows={4} className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
        </label>
        <label className="text-sm font-semibold text-[#34463f]">Proposed date and time (replaces current dates)
          <input name="proposed_date_time" type="datetime-local" className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
        </label>
        <label className="text-sm font-semibold text-[#34463f]">Proposed attendance
          <input name="expected_attendance" type="number" min={1} className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
        </label>
        {[
          ["venue_requirements", "Proposed venue requirements"],
          ["equipment_requirements", "Proposed equipment requirements"],
          ["registration_needs", "Proposed registration needs"],
        ].map(([name, label]) => (
          <label key={name} className="sm:col-span-2 text-sm font-semibold text-[#34463f]">{label}
            <textarea name={name} maxLength={2000} rows={3} className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
          </label>
        ))}
        {state.errors?.explanation ? <p className="sm:col-span-2 text-sm text-[#a23939]">{state.errors.explanation}</p> : null}
        {state.errors?.proposed_changes ? <p className="sm:col-span-2 text-sm text-[#a23939]">{state.errors.proposed_changes}</p> : null}
        {state.message ? <p role="alert" className="sm:col-span-2 text-sm text-[#a23939]">{state.message}</p> : null}
        <div className="sm:col-span-2"><button disabled={pending} className="rounded-xl bg-[#0f6b5b] px-5 py-3 text-sm font-semibold text-white disabled:opacity-60">{pending ? "Sending…" : "Request change"}</button></div>
      </form>
    </section>
  );
}
