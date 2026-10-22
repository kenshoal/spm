"use client";

import { useActionState, useId, useState } from "react";
import { decideEventChangeRequest, type TransitionState } from "../../actions";

const initialState: TransitionState = {};

/** A rejection records only the proposal outcome; it never applies its values. */
export function RejectChangeForm({
  eventRequestId,
  changeRequestId,
}: {
  eventRequestId: string;
  changeRequestId: string;
}) {
  const reasonId = useId();
  const [reason, setReason] = useState("");
  const [state, formAction, isPending] = useActionState(
    decideEventChangeRequest.bind(null, eventRequestId, changeRequestId, "Rejected"),
    initialState,
  );
  const errorId = `${reasonId}-error`;

  return (
    <form action={formAction} className="mt-4 border-t border-[#dce4e0] pt-4">
      <label htmlFor={reasonId} className="block text-sm font-semibold text-[#34463f]">
        Rejection reason (required)
      </label>
      <textarea
        id={reasonId}
        name="reason"
        required
        maxLength={2000}
        rows={3}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        disabled={isPending}
        aria-invalid={Boolean(state.errors?.reason)}
        aria-describedby={state.errors?.reason ? errorId : undefined}
        className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-3 py-2 text-sm outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb] disabled:opacity-60"
      />
      {state.errors?.reason ? (
        <p id={errorId} className="mt-1 text-sm text-[#a23939]">{state.errors.reason}</p>
      ) : null}
      {state.message ? (
        <p role="alert" className="mt-3 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]">{state.message}</p>
      ) : null}
      <button
        type="submit"
        disabled={isPending}
        className="mt-3 rounded-lg border border-[#e4b6b0] px-4 py-2.5 text-sm font-semibold text-[#a23939] hover:bg-[#fff0f0] disabled:opacity-60"
      >
        {isPending ? "Rejecting…" : "Reject change"}
      </button>
    </form>
  );
}
