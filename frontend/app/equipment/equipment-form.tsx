"use client";

import { useActionState } from "react";
import { OPERATIONAL_STATUSES, statusLabel } from "@/lib/equipment-options";
import { createEquipment, type EquipmentFormState } from "./actions";

const initialState: EquipmentFormState = {};
const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function FieldError({ message }: { message?: string }) {
  return message ? <p className="mt-1 text-sm text-[#a23939]">{message}</p> : null;
}

export function EquipmentForm() {
  const [state, formAction, isPending] = useActionState(createEquipment, initialState);
  const errors = state.errors ?? {};
  const values = state.values;
  return (
    <form action={formAction} noValidate className="grid gap-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:grid-cols-2 sm:p-8">
      <label className={labelClass}>Equipment type<input name="type" maxLength={120} defaultValue={values?.type} className={inputClass} /><FieldError message={errors.type} /></label>
      <label className={labelClass}>Home location<input name="home_location" maxLength={120} defaultValue={values?.home_location} className={inputClass} /><FieldError message={errors.home_location} /></label>
      <label className={labelClass}>Total owned quantity<input name="total_owned_quantity" type="number" min={0} step={1} defaultValue={values?.total_owned_quantity} className={inputClass} /><FieldError message={errors.total_owned_quantity} /></label>
      <label className={labelClass}>Operational status
        <select name="operational_status" defaultValue={values?.operational_status ?? "AVAILABLE"} className={inputClass}>
          {OPERATIONAL_STATUSES.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
        </select>
      </label>
      <label className={`${labelClass} sm:col-span-2`}>Description<textarea name="description" rows={3} defaultValue={values?.description} className={inputClass} /></label>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35] sm:col-span-2">{state.message}</p> : null}
      <div className="sm:col-span-2"><button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">{isPending ? "Saving…" : "Add equipment"}</button></div>
    </form>
  );
}
