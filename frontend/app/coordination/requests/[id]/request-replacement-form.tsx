"use client";

import { useActionState } from "react";
import { ConflictWarning } from "./conflict-warning";
import { requestReplacementVenue, type ReplacementState } from "./venue-booking-actions";

const initialState: ReplacementState = {};

// Offered on a flagged, approved booking: pick another venue; the event, dates and
// times stay the same.
export function RequestReplacementForm({
  bookingId,
  eventRequestId,
  venueName,
  venues,
  active,
}: {
  bookingId: string;
  eventRequestId: string;
  venueName: string;
  venues: { id: string; name: string }[];
  // A pending or approved replacement. It stands in for the form but keeps this component
  // mounted, so the clash warning from the request that just made it survives the refresh.
  active?: { venueName: string; statusLabel: string };
}) {
  const [state, formAction, isPending] = useActionState(requestReplacementVenue, initialState);
  const selectId = `replacement-venue-${bookingId}`;
  if (active) {
    return (
      <div className="mt-2">
        <p className="text-sm font-semibold text-[#33456b]">Replacement requested at {active.venueName} ({active.statusLabel})</p>
        <ConflictWarning venueName={active.venueName} conflicts={state.conflicts ?? []} />
      </div>
    );
  }
  return (
    <form action={formAction} className="mt-3 flex flex-wrap items-end gap-3">
      <input type="hidden" name="booking_id" value={bookingId} />
      <input type="hidden" name="event_request_id" value={eventRequestId} />
      <div>
        <label htmlFor={selectId} className="block text-xs font-semibold text-[#34463f]">Replacement venue</label>
        <select id={selectId} name="venue_id" defaultValue="" className="mt-1 min-h-9 rounded-lg border border-[#cfd9d4] bg-white px-2 text-sm text-[#273832]">
          <option value="">Choose a venue</option>
          {venues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name}</option>)}
        </select>
      </div>
      <button
        type="submit"
        disabled={isPending}
        aria-label={`Request replacement for ${venueName}`}
        className="min-h-9 rounded-lg bg-[#0f6b5b] px-3 text-sm font-semibold text-white hover:bg-[#0c5a4c] disabled:opacity-60"
      >
        Request replacement
      </button>
      {state.message ? <p role="alert" className="basis-full text-sm text-[#a23939]">{state.message}</p> : null}
    </form>
  );
}
