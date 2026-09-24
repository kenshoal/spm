"use client";

import { useActionState } from "react";
import { OPERATIONAL_STATUSES, statusLabel, type OperationalStatus } from "@/lib/equipment-options";
import { changeEquipmentStatus, type EquipmentFormState } from "../actions";

const initialState: EquipmentFormState = {};

export function StatusForm({ equipmentId, currentStatus }: { equipmentId: string; currentStatus: OperationalStatus }) {
  const [state, formAction, isPending] = useActionState(changeEquipmentStatus.bind(null, equipmentId, currentStatus), initialState);
  const choices = OPERATIONAL_STATUSES.filter((status) => status !== currentStatus);
  const selected = state.values && choices.includes(state.values.new_status as OperationalStatus) ? state.values.new_status : choices[0];
  const reason = state.values ? state.values.reason : "";
  return (
    <form action={formAction} className="grid gap-4 sm:grid-cols-[auto_1fr_auto] sm:items-end">
      <label className="text-sm font-semibold text-[#34463f]">New status
        <select name="new_status" defaultValue={selected} className="mt-1 block min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm">
          {choices.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
        </select>
      </label>
      <label className="text-sm font-semibold text-[#34463f]">Reason (optional)
        <input name="reason" maxLength={255} defaultValue={reason} className="mt-1 block min-h-11 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm" />
      </label>
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-semibold text-white disabled:opacity-60">{isPending ? "Saving…" : "Change status"}</button>
      {state.message ? <p role={state.saved ? "status" : "alert"} className={`rounded-lg px-3 py-2 text-sm sm:col-span-3 ${state.saved ? "bg-[#e7f5ed] text-[#145d40]" : "bg-[#fff0f0] text-[#a23939]"}`}>{state.message}</p> : null}
    </form>
  );
}
