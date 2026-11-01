"use client";

import { useActionState } from "react";
import type { EventRequest } from "@/lib/event-requests";
import { singaporeLocalValue } from "@/lib/singapore-time";
import { saveEventDetails, type SetupState } from "./event-setup-actions";

const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";
const initialState: SetupState = {};

const TEXT_FIELDS = [
  ["event_name", "Event name"],
  ["purpose", "Purpose"],
  ["description", "Description"],
  ["venue_requirements", "Venue requirements"],
  ["accessibility_needs", "Accessibility needs"],
  ["equipment_requirements", "Equipment requirements"],
  ["registration_needs", "Registration needs"],
] as const;

// Hotfix 8 (SCRUM-29, Q&A #102): the Coordinator keeps the record accurate. Changing
// dates, attendance or requirements flags existing arrangements for review; on a
// Confirmed event that returns it to Planning.
export function EventDetailsForm({ request }: { request: EventRequest }) {
  const [state, action, pending] = useActionState(saveEventDetails.bind(null, request.id), initialState);
  const dates = (request.proposed_date_times ?? []).map(singaporeLocalValue);
  return (
    <details className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <summary className="cursor-pointer text-lg font-bold text-[#17211d]">Edit event details</summary>
      <form key={request.updated_at} action={action} className="mt-4 space-y-4">
        <input type="hidden" name="expected_updated_at" value={request.updated_at} />
        {TEXT_FIELDS.map(([field, label]) => (
          <label key={field} className={labelClass}>{label}
            <input type="hidden" name={`original_${field}`} value={request[field] ?? ""} />
            <textarea name={field} rows={2} defaultValue={request[field] ?? ""} className={inputClass} />
          </label>
        ))}
        <label className={labelClass}>Expected attendance
          <input type="hidden" name="original_expected_attendance" value={request.expected_attendance ?? ""} />
          <input name="expected_attendance" type="number" min={1} step={1} defaultValue={request.expected_attendance ?? ""} className={inputClass} />
        </label>
        <fieldset>
          <legend className={labelClass}>Event dates and times (Singapore time)</legend>
          {dates.map((value, index) => (
            <div key={index}>
              <input type="hidden" name="original_proposed_date_times" value={value} />
              <input aria-label={`Date and time ${index + 1}`} name="proposed_date_times" type="datetime-local" defaultValue={value} className={inputClass} />
            </div>
          ))}
        </fieldset>
        <p className="text-xs text-[#718078]">Changing dates, attendance or requirements marks existing venue and equipment arrangements for review. A confirmed event then goes back to Planning and its organiser is told.</p>
        <button type="submit" disabled={pending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
          {pending ? "Saving…" : "Save details"}
        </button>
        {state.saved ? <p role="status" className="text-sm text-[#145c40]">Details saved.</p> : null}
        {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
      </form>
    </details>
  );
}
