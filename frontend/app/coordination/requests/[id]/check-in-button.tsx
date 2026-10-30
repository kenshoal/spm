"use client";

import { useActionState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { checkInAttendee, type CheckInState } from "../../actions";

const initialState: CheckInState = {};

/** SCRUM-25: the API rechecks assignment, event day and the registration under lock. */
export function CheckInButton({ eventRequestId, registrationId }: { eventRequestId: string; registrationId: string }) {
  const router = useRouter();
  const [state, action, pending] = useActionState(
    checkInAttendee.bind(null, eventRequestId, registrationId), initialState,
  );
  useEffect(() => {
    if (state.checkedIn) router.refresh();
  }, [state, router]);
  return (
    <form action={action}>
      <button type="submit" disabled={pending || state.checkedIn} className="min-h-9 rounded-lg border border-[#0f6b5b] px-3 text-xs font-bold text-[#0f6b5b] disabled:cursor-not-allowed disabled:opacity-60">
        {pending ? "Checking in…" : "Check in"}
      </button>
      {state.message ? <p role="alert" className="mt-1 text-xs text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
