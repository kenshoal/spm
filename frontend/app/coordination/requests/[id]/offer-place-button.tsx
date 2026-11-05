"use client";

import { useActionState } from "react";
import { offerWaitlistPlace, type SetupState } from "./event-setup-actions";

const initialState: SetupState = {};

export function OfferPlaceButton({ eventRequestId, entryId }: { eventRequestId: string; entryId: string }) {
  const [state, action, pending] = useActionState(
    async (previous: SetupState) => {
      void previous;
      return offerWaitlistPlace(eventRequestId, entryId);
    },
    initialState,
  );
  return (
    <form action={action}>
      <button type="submit" disabled={pending} className="min-h-11 rounded-lg border border-[#cfd9d4] bg-white px-3 text-sm font-semibold text-[#0f6b5b] disabled:opacity-60">
        {pending ? "Offering…" : "Offer the place"}
      </button>
      {state.message ? <p role="alert" className="mt-1 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
