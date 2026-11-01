"use client";

import { useActionState, useId, useState } from "react";
import { setRequirementEssential, type SetupState } from "./event-setup-actions";

const initialState: SetupState = {};

/**
 * Hotfix 25 (Q&A #80, #106): the Coordinator, with Technical Support, decides a requirement is not
 * essential, so the event can be confirmed without it; or puts it back.
 */
export function EssentialForm({ eventRequestId, requirementId, essential }: {
  eventRequestId: string;
  requirementId: string;
  essential: boolean;
}) {
  const id = useId();
  const [note, setNote] = useState("");
  const [state, action, pending] = useActionState(
    async (previous: SetupState, formData: FormData) => {
      const next = await setRequirementEssential(eventRequestId, requirementId, previous, formData);
      if (next.saved) setNote("");
      return next;
    },
    initialState,
  );
  return (
    <form action={action} className="mt-2 flex flex-wrap items-end gap-2">
      <input type="hidden" name="essential" value={essential ? "false" : "true"} />
      {essential ? (
        <div className="min-w-0 flex-1">
          <label htmlFor={`${id}-note`} className="block text-xs font-semibold text-[#34463f]">Not essential: what was agreed with Technical Support?</label>
          <input id={`${id}-note`} name="note" maxLength={2000} required value={note} onChange={(event) => setNote(event.target.value)} disabled={pending} className="mt-1 min-h-11 w-full rounded-lg border border-[#cfd9d4] px-3 text-sm" />
        </div>
      ) : null}
      <button type="submit" disabled={pending} className="min-h-11 rounded-lg border border-[#cfd9d4] bg-white px-3 text-xs font-bold text-[#0f6b5b] hover:bg-[#f4f7f5] disabled:opacity-60">
        {pending ? "Saving…" : essential ? "Mark not essential" : "Mark essential again"}
      </button>
      {state.message ? <p role="alert" className="w-full text-xs text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
