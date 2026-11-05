"use client";

import { useActionState } from "react";
import { singaporeLocalValue } from "@/lib/singapore-time";
import { saveRegistrationSettings, type SetupState } from "./event-setup-actions";

const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";
const initialState: SetupState = {};

// Hotfix 4 (Q&A #30, #42, #127): set, extend or reopen registration, in Singapore time.
export function RegistrationSettingsForm({ eventRequestId, opensAt, closesAt, capacity }: {
  eventRequestId: string;
  opensAt: string | null;
  closesAt: string | null;
  capacity: number | null;
}) {
  const [state, action, pending] = useActionState(saveRegistrationSettings.bind(null, eventRequestId), initialState);
  return (
    <form action={action} className="mt-4 space-y-4 border-t border-[#e3ebe7] pt-4">
      <h3 className="text-sm font-bold text-[#17211d]">Registration period and capacity</h3>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className={labelClass}>Opens<input name="registration_opens_at" type="datetime-local" defaultValue={singaporeLocalValue(opensAt)} className={inputClass} /></label>
        <label className={labelClass}>Closes<input name="registration_closes_at" type="datetime-local" defaultValue={singaporeLocalValue(closesAt)} className={inputClass} /></label>
        <label className={labelClass}>Capacity<input name="registration_capacity" type="number" min={1} step={1} defaultValue={capacity ?? ""} className={inputClass} /></label>
      </div>
      <p className="text-xs text-[#718078]">Singapore time. Attendees can register once the event is confirmed and registration is open.</p>
      <button type="submit" disabled={pending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {pending ? "Saving…" : "Save registration settings"}
      </button>
      {state.saved ? <p role="status" className="text-sm text-[#145c40]">Registration settings saved.</p> : null}
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
