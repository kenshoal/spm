"use client";

import { useActionState, useRef, useState } from "react";
import { createEventChangeRequest } from "../actions";

export function ChangeRequestForm({ eventRequestId }: { eventRequestId: string }) {
  const [dates, setDates] = useState([{ id: 0, value: "" }]);
  const nextDate = useRef(1);
  const action = createEventChangeRequest.bind(null, eventRequestId);
  const [state, formAction, pending] = useActionState(action, {});
  if (state.submitted) {
    return <div role="status" className="rounded-xl border border-[#bcd9ce] bg-[#edf7f3] px-4 py-3 text-sm text-[#145c40]">Your change request was saved for the assigned coordinator to review. The event plan remains unchanged.</div>;
  }
  return (
    <section aria-labelledby="request-change-title" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 id="request-change-title" className="pr-16 text-lg font-bold text-[#17211d]">Request a change</h2>
      <p className="mt-2 text-sm leading-6 text-[#68776f]">Only complete the event details that should change. Pending proposals limited to attendance, venue requirements, equipment requirements and registration requirements can be approved by the assigned coordinator. Date changes require the coordinator to review a complete venue booking plan; the entire change is refused if any booking conflicts. Registration requirements do not change attendees, capacity or registration windows. The coordinator can reject a proposal with a reason. Sending a proposal leaves the current event plan unchanged.</p>
      <form action={formAction} className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="sm:col-span-2 text-sm font-semibold text-[#34463f]">Reason for change
          <textarea name="explanation" required maxLength={2000} rows={4} className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
        </label>
        <fieldset className="sm:col-span-2 space-y-3" disabled={pending}>
          <legend className="text-sm font-semibold text-[#34463f]">Proposed dates and times (replaces the whole current list)</legend>
          <p className="text-sm text-[#68776f]">Enter every replacement event date in order. Blank rows do not propose a date change.</p>
          {dates.map((date, index) => <div key={date.id} className="flex flex-wrap items-end gap-2">
            <label className="min-w-0 flex-1 text-sm">Proposed date and time {index + 1}
              <input name="proposed_date_time" type="datetime-local" value={date.value} onChange={(event) => setDates((current) => current.map((row) => row.id === date.id ? { ...row, value: event.target.value } : row))} className="mt-1 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
            </label>
            {dates.length > 1 ? <button type="button" onClick={() => setDates((current) => current.filter((row) => row.id !== date.id))} className="min-h-11 rounded-lg border border-[#cfd9d4] px-3 py-2 text-sm" aria-label={`Remove date and time ${index + 1}`}>Remove</button> : null}
          </div>)}
          <button type="button" onClick={() => { const id = nextDate.current++; setDates((current) => [...current, { id, value: "" }]); }} className="min-h-11 rounded-lg border border-[#0f6b5b] px-3 py-2 text-sm text-[#0f6b5b]">Add proposed date</button>
        </fieldset>
        <label className="text-sm font-semibold text-[#34463f]">Proposed attendance
          <input name="expected_attendance" type="number" min={1} className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
        </label>
        {[
          ["venue_requirements", "Proposed venue requirements"],
          ["equipment_requirements", "Proposed equipment requirements"],
          ["registration_needs", "Proposed registration needs"],
          ["accessibility_needs", "Proposed accessibility needs"],
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
