"use client";

import { useActionState } from "react";
import { TimeRangeFields } from "@/app/components/time-range-fields";
import { layoutLabel, ROOM_LAYOUTS } from "@/lib/venue-options";
import { ATTRIBUTE_LABELS, type SuitabilityFormValues, type SuitabilityResult } from "@/lib/venue-suitability";
import { checkVenueSuitability, type SuitabilityState } from "./actions";

const initialState: SuitabilityState = {};
const inputClass = "mt-1 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 py-2 text-sm text-[#273832]";
const labelClass = "block text-xs font-semibold text-[#34463f]";

// The verdict is written in words, so it never relies on colour alone.
export function SuitabilityVerdict({ result }: { result: SuitabilityResult }) {
  return (
    <div role="status" className={`mt-3 rounded-xl border px-4 py-3 text-sm ${result.suitable ? "border-[#bcdccf] bg-[#f1faf6] text-[#17493e]" : "border-[#eccdbe] bg-[#fff8f3] text-[#793f27]"}`}>
      <p className="font-bold">{result.suitable ? "Suitable" : "Not suitable"}</p>
      {result.mismatches.length ? (
        <ul className="mt-2 space-y-1">
          {result.mismatches.map((mismatch) => (
            <li key={mismatch.attribute}><span className="font-semibold">{ATTRIBUTE_LABELS[mismatch.attribute]}</span>: {mismatch.reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function SuitabilityCheck({ venueId, defaults }: { venueId: string; defaults: SuitabilityFormValues }) {
  const [state, formAction, isPending] = useActionState(checkVenueSuitability.bind(null, venueId), initialState);
  const values = state.values ?? defaults;
  const errors = state.errors ?? {};

  return (
    <details className="mt-4 border-t border-[#e6ede9] pt-3">
      <summary className="cursor-pointer text-sm font-semibold text-[#0f6b5b]">Check suitability</summary>
      <form action={formAction} noValidate className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className={labelClass}>Expected attendance<input name="expected_attendance" type="number" min={1} step={1} defaultValue={values.expected_attendance} className={inputClass} />{errors.expected_attendance ? <span role="alert" className="mt-1 block font-normal text-[#a23939]">{errors.expected_attendance}</span> : null}</label>
        <label className={labelClass}>Required layout
          <select name="required_layout" defaultValue={values.required_layout} className={inputClass}>
            <option value="">Any layout</option>
            {ROOM_LAYOUTS.map((layout) => <option key={layout} value={layout}>{layoutLabel(layout)}</option>)}
          </select>
        </label>
        <div className="sm:col-span-2">
          <TimeRangeFields start={values.start_time} end={values.end_time} errors={errors} inputClass={inputClass} labelClass={labelClass} optional />
        </div>
        <label className={labelClass}>Required facilities<input name="required_facilities" defaultValue={values.required_facilities} placeholder="Projector, WiFi" className={inputClass} /></label>
        <label className={`${labelClass} sm:col-span-2`}>Required accessibility<input name="required_accessibility" defaultValue={values.required_accessibility} placeholder="Ramp access" className={inputClass} /></label>
        <div className="sm:col-span-2"><button type="submit" disabled={isPending} className="min-h-10 rounded-xl border border-[#0f6b5b] px-4 text-sm font-bold text-[#0f6b5b] hover:bg-[#f1faf6] disabled:opacity-60">Check this venue</button></div>
      </form>
      {state.message ? <p role="alert" className="mt-3 text-sm text-[#a23939]">{state.message}</p> : null}
      {state.result ? <SuitabilityVerdict result={state.result} /> : null}
    </details>
  );
}
