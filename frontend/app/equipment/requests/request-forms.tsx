"use client";

import { useActionState } from "react";
import {
  checkAvailability,
  releaseReservation,
  reserveEquipment,
  updateArrangement,
  type RequestActionState,
} from "./actions";

const inputClass = "mt-1 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 py-2 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";
const buttonClass = "min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60";
const initialState: RequestActionState = {};

function Outcome({ state, done }: { state: RequestActionState; done: string }) {
  return (
    <>
      {state.done ? <p role="status" className="text-sm text-[#145c40]">{done}</p> : null}
      {state.lines?.map((line) => <p key={line} role="status" className="text-sm text-[#273832]">{line}</p>)}
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-3 py-2 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </>
  );
}

interface Defaults {
  venues: { id: string; name: string }[];
  startDate: string;
  endDate: string;
  quantity: number;
}

function DateAndVenueFields({ defaults }: { defaults: Defaults }) {
  return (
    <>
      <label className={labelClass}>Venue
        <select name="venue_id" defaultValue="" className={inputClass}>
          <option value="">Choose</option>
          {defaults.venues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name}</option>)}
        </select>
      </label>
      <label className={labelClass}>From<input name="start_date" type="date" defaultValue={defaults.startDate} className={inputClass} /></label>
      <label className={labelClass}>To<input name="end_date" type="date" defaultValue={defaults.endDate} className={inputClass} /></label>
    </>
  );
}

export function AvailabilityForm({ requirementId, equipmentType, defaults }: { requirementId: string; equipmentType: string; defaults: Defaults }) {
  const [state, action, pending] = useActionState(checkAvailability.bind(null, requirementId, equipmentType), initialState);
  return (
    <form action={action} className="grid gap-3 sm:grid-cols-5 sm:items-end">
      <DateAndVenueFields defaults={defaults} />
      <label className={labelClass}>Quantity<input name="quantity" type="number" min={1} defaultValue={defaults.quantity} className={inputClass} /></label>
      <button type="submit" disabled={pending} className={buttonClass}>{pending ? "Checking…" : "Check availability"}</button>
      <div className="sm:col-span-5"><Outcome state={state} done="" /></div>
    </form>
  );
}

export function ReserveForm({ requirementId, defaults, equipment }: { requirementId: string; defaults: Defaults; equipment: { id: string; label: string }[] }) {
  const [state, action, pending] = useActionState(reserveEquipment.bind(null, requirementId), initialState);
  return (
    <form action={action} className="grid gap-3 sm:grid-cols-6 sm:items-end">
      <label className={labelClass}>Equipment
        <select name="equipment_id" defaultValue="" className={inputClass}>
          <option value="">Choose</option>
          {equipment.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </label>
      <DateAndVenueFields defaults={defaults} />
      <label className={labelClass}>Quantity<input name="quantity" type="number" min={1} defaultValue={defaults.quantity} className={inputClass} /></label>
      <button type="submit" disabled={pending} className={buttonClass}>{pending ? "Reserving…" : "Reserve"}</button>
      <div className="sm:col-span-6"><Outcome state={state} done="Reserved." /></div>
    </form>
  );
}

export function ReleaseForm({ reservationId }: { reservationId: string }) {
  const [state, action, pending] = useActionState(releaseReservation.bind(null, reservationId), initialState);
  return (
    <form action={action} className="flex flex-wrap items-end gap-2">
      <label className={`${labelClass} min-w-0 flex-1`}>Reason to release<input name="reason" maxLength={2000} className={inputClass} /></label>
      <button type="submit" disabled={pending} className="min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-4 text-sm font-semibold text-[#8e3d35] disabled:opacity-60">{pending ? "Releasing…" : "Release"}</button>
      <div className="w-full"><Outcome state={state} done="Released." /></div>
    </form>
  );
}

export function ArrangementForm({ requirementId, status, note }: { requirementId: string; status: string; note: string | null }) {
  const [state, action, pending] = useActionState(updateArrangement.bind(null, requirementId, status), initialState);
  return (
    <form action={action} className="grid gap-3 sm:grid-cols-4 sm:items-end">
      <label className={labelClass}>Status
        <select name="status" defaultValue={status} className={inputClass}>
          <option value="requested">Requested</option>
          <option value="in_progress">In progress</option>
          <option value="arranged">Arranged</option>
        </select>
      </label>
      <label className={`${labelClass} sm:col-span-2`}>Note for the coordinator<input name="support_note" defaultValue={note ?? ""} maxLength={2000} className={inputClass} /></label>
      <button type="submit" disabled={pending} className={buttonClass}>{pending ? "Saving…" : "Update"}</button>
      <div className="sm:col-span-4"><Outcome state={state} done="Updated." /></div>
    </form>
  );
}
