"use client";

import { useActionState } from "react";
import { decideEventChangeRequest, type TransitionState } from "../../actions";

const initialState: TransitionState = {};

/** Apply only the server-validated non-date proposal; the action refreshes its audit. */
export function ApproveChangeForm({
  eventRequestId,
  changeRequestId,
}: {
  eventRequestId: string;
  changeRequestId: string;
}) {
  const [state, formAction, isPending] = useActionState(
    decideEventChangeRequest.bind(null, eventRequestId, changeRequestId, "Approved"),
    initialState,
  );

  return (
    <form action={formAction} aria-busy={isPending} className="mt-4">
      {state.message ? (
        <p role="alert" className="mb-3 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]">{state.message}</p>
      ) : null}
      <button
        type="submit"
        disabled={isPending}
        className="rounded-lg bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0c594b] disabled:opacity-60"
      >
        {isPending ? "Approving…" : "Approve change"}
      </button>
    </form>
  );
}
