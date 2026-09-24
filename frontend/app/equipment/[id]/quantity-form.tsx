"use client";

import { useActionState } from "react";
import { updateEquipmentQuantity, type EquipmentFormState } from "../actions";

const initialState: EquipmentFormState = {};

export function QuantityForm({ equipmentId, quantity }: { equipmentId: string; quantity: number }) {
  const [state, formAction, isPending] = useActionState(updateEquipmentQuantity.bind(null, equipmentId), initialState);
  // Gate on whether `values` is present at all, never a per-field fallback: an
  // invalid raw entry (e.g. "2.5") must be shown exactly as typed, never
  // silently replaced by the stored quantity.
  const value = state.values ? state.values.total_owned_quantity : quantity;
  return (
    <form action={formAction} noValidate className="flex flex-wrap items-end gap-3">
      <label className="text-sm font-semibold text-[#34463f]">Total owned quantity
        <input name="total_owned_quantity" type="number" min={0} step={1} defaultValue={value} className="mt-1 block min-h-11 w-40 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm" />
      </label>
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-semibold text-white disabled:opacity-60">{isPending ? "Saving…" : "Update quantity"}</button>
      {state.message ? <p role={state.saved ? "status" : "alert"} className={`w-full rounded-lg px-3 py-2 text-sm ${state.saved ? "bg-[#e7f5ed] text-[#145d40]" : "bg-[#fff0f0] text-[#a23939]"}`}>{state.message}</p> : null}
    </form>
  );
}
