"use client";

import { useActionState } from "react";
import { layoutLabel, MAX_PREP_MINUTES, PREP_MINUTES_STEP, ROOM_LAYOUTS } from "@/lib/venue-options";
import type { Venue } from "@/lib/venues";
import { createVenue, updateVenue, type VenueFormState } from "./actions";

const initialState: VenueFormState = {};
const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832] outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function FieldError({ message }: { message?: string }) {
  return message ? <p className="mt-1 text-sm text-[#a23939]">{message}</p> : null;
}

export function VenueForm({ venue }: { venue?: Venue }) {
  const action = venue ? updateVenue.bind(null, venue.id) : createVenue;
  const [state, formAction, isPending] = useActionState(action, initialState);
  const errors = state.errors ?? {};
  // React resets a <form>'s uncontrolled fields to their rendered defaultValue
  // the moment an action is submitted (before it even resolves), so a
  // corrected resubmission must re-derive every default from the last
  // submitted values. This falls back to `venue` (or blank) only when there
  // is no echoed submission at all — never per field — so an individually
  // invalid field (e.g. a non-numeric capacity) shows exactly what was typed
  // instead of silently reverting to the venue's stored value.
  const values = state.values;

  return (
    <form action={formAction} noValidate className="space-y-6 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        <label className={labelClass}>Venue name<input name="name" defaultValue={values ? values.name : venue?.name} className={inputClass} /><FieldError message={errors.name} /></label>
        <label className={labelClass}>Location<input name="location" defaultValue={values ? values.location : venue?.location} className={inputClass} /><FieldError message={errors.location} /></label>
        <label className={labelClass}>Maximum capacity<input name="max_capacity" type="number" min={1} step={1} defaultValue={values ? values.max_capacity : venue?.max_capacity} className={inputClass} /><FieldError message={errors.max_capacity} /></label>
        {venue ? (
          <label className={labelClass}>Availability
            <select name="status" defaultValue={values ? values.status : venue.status} className={inputClass}>
              <option value="available">Available</option>
              <option value="blocked">Blocked — hidden from venue search</option>
            </select>
          </label>
        ) : null}
        <label className={labelClass}>Setup time (minutes)<input name="setup_minutes" type="number" min={0} max={MAX_PREP_MINUTES} step={PREP_MINUTES_STEP} defaultValue={values ? values.setup_minutes : venue?.setup_minutes ?? 0} className={inputClass} /><FieldError message={errors.setup_minutes} /></label>
        <label className={labelClass}>Turnaround time (minutes)<input name="turnaround_minutes" type="number" min={0} max={MAX_PREP_MINUTES} step={PREP_MINUTES_STEP} defaultValue={values ? values.turnaround_minutes : venue?.turnaround_minutes ?? 0} className={inputClass} /><FieldError message={errors.turnaround_minutes} /></label>
        <p className="-mt-3 text-xs text-[#718078] sm:col-span-2">Time to prepare the venue before an event and reset it after, in steps of {PREP_MINUTES_STEP} minutes. Use 0 for none.</p>
        <div className="sm:col-span-2"><label className={labelClass}>Facilities<input name="facilities" defaultValue={values ? values.facilities : venue?.facilities.join(", ")} placeholder="Projector, WiFi, Stage" className={inputClass} /></label><p className="mt-1 text-xs text-[#718078]">Separate items with commas.</p></div>
        <div className="sm:col-span-2"><label className={labelClass}>Accessibility features<input name="accessibility_features" defaultValue={values ? values.accessibility_features : venue?.accessibility_features.join(", ")} placeholder="Ramp access, Hearing loop" className={inputClass} /></label><p className="mt-1 text-xs text-[#718078]">Separate items with commas.</p></div>
      </div>
      <fieldset>
        <legend className={labelClass}>Supported room layouts</legend>
        <div className="mt-2 flex flex-wrap gap-4">
          {ROOM_LAYOUTS.map((layout) => (
            <label key={layout} className="inline-flex items-center gap-2 text-sm text-[#273832]">
              <input type="checkbox" name="supported_layouts" value={layout} defaultChecked={values ? values.supported_layouts.includes(layout) : venue?.supported_layouts.includes(layout)} />
              {layoutLabel(layout)}
            </label>
          ))}
        </div>
      </fieldset>
      <p className="text-xs text-[#718078]">Every venue is bookable from 07:00 to 24:00 in 15-minute steps.</p>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {isPending ? "Saving…" : venue ? "Save changes" : "Add venue"}
      </button>
    </form>
  );
}
