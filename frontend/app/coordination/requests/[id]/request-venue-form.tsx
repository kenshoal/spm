"use client";

import { useActionState } from "react";
import { TimeRangeFields } from "@/app/components/time-range-fields";
import { ConflictWarning } from "./conflict-warning";
import { requestVenueBooking, type RequestVenueState } from "./venue-booking-actions";

const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";
const initialState: RequestVenueState = {};

// Hotfix 6 (SCRUM-32, SCRUM-61): request a venue, or another one, for this event.
export function RequestVenueForm({ eventRequestId, venues }: { eventRequestId: string; venues: { id: string; name: string }[] }) {
  const [state, action, pending] = useActionState(requestVenueBooking.bind(null, eventRequestId), initialState);
  return (
    <form action={action} className="mt-5 space-y-4 border-t border-[#eef2f0] pt-4">
      <h3 className="text-sm font-bold text-[#17211d]">Request a venue</h3>
      <label className={labelClass}>Venue
        <select name="venue_id" defaultValue="" className={inputClass}>
          <option value="">Choose</option>
          {venues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name}</option>)}
        </select>
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>Start date<input name="start_date" type="date" className={inputClass} /></label>
        <label className={labelClass}>End date<input name="end_date" type="date" className={inputClass} /></label>
      </div>
      <TimeRangeFields inputClass={inputClass} labelClass={labelClass} />
      <button type="submit" disabled={pending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {pending ? "Requesting…" : "Request venue"}
      </button>
      {state.submitted ? <p role="status" className="text-sm text-[#145c40]">Request sent to Venue Staff.</p> : null}
      {state.conflicts?.length ? <ConflictWarning venueName="This venue" conflicts={state.conflicts} /> : null}
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
