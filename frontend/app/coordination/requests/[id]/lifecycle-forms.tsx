"use client";

import { useActionState, useId, useState } from "react";
import {
  changeOrganiser,
  postponeEvent,
  resumeEvent,
  type SetupState,
} from "./event-setup-actions";

const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";
const buttonClass = "min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60";
const initialState: SetupState = {};

function Feedback({ state, saved }: { state: SetupState; saved: string }) {
  return (
    <>
      {state.saved ? <p role="status" className="text-sm text-[#145c40]">{saved}</p> : null}
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </>
  );
}

/** Hotfix 22 (Q&A #69, #121): postpone with no new date; bookings and reservations are released. */
export function PostponeEventForm({ eventRequestId }: { eventRequestId: string }) {
  const id = useId();
  // Controlled: React clears uncontrolled fields after an action, losing the text on a refusal.
  const [reason, setReason] = useState("");
  const [state, action, pending] = useActionState(
    async (previous: SetupState, formData: FormData) => {
      const next = await postponeEvent(eventRequestId, previous, formData);
      if (next.saved) setReason("");
      return next;
    },
    initialState,
  );
  return (
    <details className="mt-4 border-t border-[#e3ebe7] pt-4">
    <summary className="cursor-pointer text-sm font-bold text-[#17211d]">Postpone this event</summary>
    <form action={action} className="mt-3 space-y-3">
      <p className="text-xs leading-5 text-[#718078]">
        Use this when the event cannot go ahead on its date and there is no new date yet. Its venue bookings, holds and
        equipment reservations are released; the event, its requirements and its registrations are kept. The organiser,
        the registered attendees and the staff involved are told.
      </p>
      <label htmlFor={`${id}-reason`} className={labelClass}>Reason</label>
      <textarea id={`${id}-reason`} name="reason" rows={2} maxLength={2000} required value={reason} onChange={(event) => setReason(event.target.value)} disabled={pending} className={inputClass} />
      <button type="submit" disabled={pending} className={buttonClass}>{pending ? "Postponing…" : "Postpone event"}</button>
      <Feedback state={state} saved="The event is postponed." />
    </form>
    </details>
  );
}

/** Hotfix 22: give a postponed event its new date; it goes back to Planning. */
export function ResumeEventForm({ eventRequestId }: { eventRequestId: string }) {
  const id = useId();
  const [date, setDate] = useState("");
  const [state, action, pending] = useActionState(
    async (previous: SetupState, formData: FormData) => {
      const next = await resumeEvent(eventRequestId, previous, formData);
      if (next.saved) setDate("");
      return next;
    },
    initialState,
  );
  return (
    <form action={action} className="mt-4 space-y-3 border-t border-[#e3ebe7] pt-4">
      <h3 className="text-sm font-bold text-[#17211d]">Set the new date</h3>
      <p className="text-xs leading-5 text-[#718078]">
        Once the new date is set the event returns to Planning. Its venues and equipment were released, so they are booked
        and confirmed again for the new date.
      </p>
      <label htmlFor={`${id}-date`} className={labelClass}>New date and time (Singapore time)</label>
      <input id={`${id}-date`} name="new_date" type="datetime-local" required value={date} onChange={(event) => setDate(event.target.value)} disabled={pending} className={inputClass} />
      <button type="submit" disabled={pending} className={buttonClass}>{pending ? "Saving…" : "Set new date"}</button>
      <Feedback state={state} saved="The new date is set." />
    </form>
  );
}

/** Hotfix 24 (Q&A #59, #61): hand the event to another Event Organiser. */
export function ChangeOrganiserForm({ eventRequestId }: { eventRequestId: string }) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const [state, action, pending] = useActionState(
    async (previous: SetupState, formData: FormData) => {
      const next = await changeOrganiser(eventRequestId, previous, formData);
      if (next.saved) {
        setEmail("");
        setReason("");
      }
      return next;
    },
    initialState,
  );
  return (
    <details className="mt-4 border-t border-[#e3ebe7] pt-4">
    <summary className="cursor-pointer text-sm font-bold text-[#17211d]">Change the Event Organiser</summary>
    <form action={action} className="mt-3 space-y-3">
      <p className="text-xs leading-5 text-[#718078]">
        For when the organiser has left or their account is closed. The new organiser must already have an Event Organiser
        account (and be in the client organisation, if the event has one). Both people are told.
      </p>
      <label htmlFor={`${id}-email`} className={labelClass}>New organiser&apos;s email</label>
      <input id={`${id}-email`} name="organiser_email" type="email" required autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} disabled={pending} className={inputClass} />
      <label htmlFor={`${id}-reason`} className={labelClass}>Reason</label>
      <textarea id={`${id}-reason`} name="reason" rows={2} maxLength={2000} required value={reason} onChange={(event) => setReason(event.target.value)} disabled={pending} className={inputClass} />
      <button type="submit" disabled={pending} className={buttonClass}>{pending ? "Changing…" : "Change organiser"}</button>
      <Feedback state={state} saved="The Event Organiser is changed." />
    </form>
    </details>
  );
}
