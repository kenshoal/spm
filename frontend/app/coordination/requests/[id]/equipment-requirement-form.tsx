"use client";

import { useActionState } from "react";
import { recordEquipmentRequirement, type SetupState } from "./event-setup-actions";

const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";
const initialState: SetupState = {};

export function EquipmentRequirementForm({ eventRequestId, types }: { eventRequestId: string; types: string[] }) {
  const [state, action, pending] = useActionState(recordEquipmentRequirement.bind(null, eventRequestId), initialState);
  return (
    <form action={action} className="mt-5 space-y-4 border-t border-[#eef2f0] pt-4">
      <h3 className="text-sm font-bold text-[#17211d]">Record equipment needed</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>Equipment type
          <input name="equipment_type" list="equipment-types" className={inputClass} />
          <datalist id="equipment-types">{types.map((type) => <option key={type} value={type} />)}</datalist>
        </label>
        <label className={labelClass}>Quantity<input name="quantity" type="number" min={1} step={1} className={inputClass} /></label>
      </div>
      <label className={labelClass}>Technical requirements (optional)<textarea name="technical_requirements" rows={2} maxLength={2000} className={inputClass} /></label>
      <button type="submit" disabled={pending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {pending ? "Recording…" : "Record equipment"}
      </button>
      {state.saved ? <p role="status" className="text-sm text-[#145c40]">Equipment recorded for Technical Support.</p> : null}
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
