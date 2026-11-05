"use client";

import { useActionState, useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import { registerAttendee, type ManualRegistrationState } from "../../actions";

const initialState: ManualRegistrationState = {};

/** SCRUM-41: registers an existing attendee account; the API rechecks everything under lock. */
export function ManualRegistrationForm({ eventRequestId, vipPlaces = 0 }: { eventRequestId: string; vipPlaces?: number }) {
  const inputId = useId();
  // Controlled: React resets uncontrolled fields after an action, losing the email on a refusal.
  const [email, setEmail] = useState("");
  const router = useRouter();
  const [state, action, pending] = useActionState(
    async (previous: ManualRegistrationState, formData: FormData) => {
      const next = await registerAttendee(eventRequestId, previous, formData);
      if (next.registered) setEmail("");
      return next;
    },
    initialState,
  );
  useEffect(() => {
    if (state.registered) router.refresh();
  }, [state, router]);
  return (
    <form action={action} className="mt-4 flex flex-wrap items-end gap-3 border-t border-[#e3ebe7] pt-4">
      <div className="min-w-0 flex-1">
        <label htmlFor={inputId} className="block text-sm font-semibold text-[#34463f]">Attendee email</label>
        <input id={inputId} name="attendee_email" type="email" required autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} disabled={pending} className="mt-1 min-h-11 w-full rounded-lg border border-[#cfd9d4] px-3 text-sm" />
      </div>
      {vipPlaces > 0 ? (
        <p className="w-full text-xs text-[#68776f]">
          Normal registration is full. You can still add {vipPlaces} more {vipPlaces === 1 ? "person" : "people"} up to the venue&apos;s capacity.
        </p>
      ) : null}
      <button type="submit" disabled={pending} className="min-h-11 rounded-lg bg-[#0f6b5b] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60">
        {pending ? "Adding…" : "Add attendee"}
      </button>
      {state.message ? <p role="alert" className="w-full text-sm text-[#8e3d35]">{state.message}</p> : null}
      {state.registered ? <p role="status" className="w-full text-sm text-[#145c40]">Attendee added.</p> : null}
    </form>
  );
}
