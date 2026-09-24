"use client";

import { useActionState } from "react";
import type { RoomLayout, Slot, Venue } from "@/lib/venues";
import { createVenue, updateVenue, type VenueFormState } from "./actions";

// Mirrors lib/venues.ts's ROOM_LAYOUTS, SLOTS and layoutLabel by value rather
// than importing them: this is a "use client" module, and lib/venues.ts pulls
// in lib/api.ts (server-only, via next/headers) to fetch venues. Importing
// runtime values from it here would ship that server code to the browser
// bundle and fail the build — only type-only imports from lib/venues.ts are
// safe in a client component (see app/operations/assignments/assign-coordinator-form.tsx
// for the same pattern with CoordinatorOption).
const ROOM_LAYOUTS: readonly RoomLayout[] = ["classroom", "theatre", "boardroom", "banquet", "exhibition"];
const SLOTS: readonly Slot[] = ["AM", "PM", "NIGHT"];
function layoutLabel(layout: RoomLayout): string {
  return layout.charAt(0).toUpperCase() + layout.slice(1);
}

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
  // submitted payload — falling back to the venue being edited, then blank —
  // or the fields the user didn't just touch would be wiped out too.
  const values = state.values;

  return (
    <form action={formAction} noValidate className="space-y-6 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        <label className={labelClass}>Venue name<input name="name" defaultValue={values?.name ?? venue?.name} className={inputClass} /><FieldError message={errors.name} /></label>
        <label className={labelClass}>Location<input name="location" defaultValue={values?.location ?? venue?.location} className={inputClass} /><FieldError message={errors.location} /></label>
        <label className={labelClass}>Maximum capacity<input name="max_capacity" type="number" min={1} step={1} defaultValue={values?.max_capacity ?? venue?.max_capacity} className={inputClass} /><FieldError message={errors.max_capacity} /></label>
        {venue ? (
          <label className={labelClass}>Availability
            <select name="status" defaultValue={values?.status ?? venue.status} className={inputClass}>
              <option value="available">Available</option>
              <option value="blocked">Blocked — hidden from venue search</option>
            </select>
          </label>
        ) : null}
        <div className="sm:col-span-2"><label className={labelClass}>Facilities<input name="facilities" defaultValue={(values?.facilities ?? venue?.facilities)?.join(", ")} placeholder="Projector, WiFi, Stage" className={inputClass} /></label><p className="mt-1 text-xs text-[#718078]">Separate items with commas.</p></div>
        <div className="sm:col-span-2"><label className={labelClass}>Accessibility features<input name="accessibility_features" defaultValue={(values?.accessibility_features ?? venue?.accessibility_features)?.join(", ")} placeholder="Ramp access, Hearing loop" className={inputClass} /></label><p className="mt-1 text-xs text-[#718078]">Separate items with commas.</p></div>
      </div>
      <fieldset>
        <legend className={labelClass}>Supported room layouts</legend>
        <div className="mt-2 flex flex-wrap gap-4">
          {ROOM_LAYOUTS.map((layout) => (
            <label key={layout} className="inline-flex items-center gap-2 text-sm text-[#273832]">
              <input type="checkbox" name="supported_layouts" value={layout} defaultChecked={(values?.supported_layouts ?? venue?.supported_layouts)?.includes(layout)} />
              {layoutLabel(layout)}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className={labelClass}>Operating slots</legend>
        <div className="mt-2 flex flex-wrap gap-4">
          {SLOTS.map((slot) => (
            <label key={slot} className="inline-flex items-center gap-2 text-sm text-[#273832]">
              <input type="checkbox" name="operating_slots" value={slot} defaultChecked={values ? values.operating_slots.includes(slot) : venue ? venue.operating_slots.includes(slot) : true} />
              {slot}
            </label>
          ))}
        </div>
        <FieldError message={errors.operating_slots} />
      </fieldset>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {isPending ? "Saving…" : venue ? "Save changes" : "Add venue"}
      </button>
    </form>
  );
}
