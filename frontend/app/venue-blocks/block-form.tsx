"use client";

import { useActionState } from "react";
import { BLOCK_REASONS, REASON_DETAIL_MAX, reasonLabel } from "@/lib/venue-block-options";
import { TimeRangeFields } from "@/app/components/time-range-fields";
import { createVenueBlock, type BlockFormState } from "./actions";

const initialState: BlockFormState = {};
const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832] outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function FieldError({ message }: { message?: string }) {
  return message ? <p className="mt-1 text-sm text-[#a23939]">{message}</p> : null;
}

export function BlockForm({ venues, selectedVenueId }: { venues: { id: string; name: string }[]; selectedVenueId: string }) {
  const [state, formAction, isPending] = useActionState(createVenueBlock, initialState);
  const errors = state.errors ?? {};
  // React resets uncontrolled fields on submit, so a failed submission
  // re-derives every default from the echoed values (see venue-form.tsx).
  const values = state.values;

  return (
    <form action={formAction} noValidate aria-label="Block a venue" className="space-y-5 rounded-2xl border border-[#dce4e0] bg-white p-6">
      <h2 className="text-lg font-bold text-[#1b2b25]">Block a venue</h2>
      <label className={labelClass}>Venue
        <select name="venue_id" defaultValue={values ? values.venue_id : selectedVenueId} className={inputClass}>
          {venues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name}</option>)}
        </select>
        <FieldError message={errors.venue_id} />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>Start date<input name="start_date" type="date" defaultValue={values?.start_date} className={inputClass} /><FieldError message={errors.start_date} /></label>
        <label className={labelClass}>End date<input name="end_date" type="date" defaultValue={values?.end_date} className={inputClass} /><FieldError message={errors.end_date} /></label>
      </div>
      <div>
        <TimeRangeFields start={values?.start_time} end={values?.end_time} errors={errors} inputClass={inputClass} labelClass={labelClass} />
        <p className="mt-1 text-xs text-[#718078]">Blocked at these times on every date in the range.</p>
      </div>
      <label className={labelClass}>Reason
        <select name="reason_category" defaultValue={values?.reason_category ?? ""} className={inputClass}>
          <option value="">Choose a reason</option>
          {BLOCK_REASONS.map((reason) => <option key={reason} value={reason}>{reasonLabel(reason)}</option>)}
        </select>
        <FieldError message={errors.reason_category} />
      </label>
      <label className={labelClass}>Detail (optional)
        <textarea name="reason_detail" rows={3} maxLength={REASON_DETAIL_MAX} defaultValue={values?.reason_detail} placeholder="e.g. Air-conditioning repairs" className={inputClass} />
        <FieldError message={errors.reason_detail} />
      </label>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {isPending ? "Saving…" : "Block venue"}
      </button>
    </form>
  );
}
