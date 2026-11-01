"use client";

import { useActionState, useId, useState } from "react";
import { CHANGE_FIELD_LABELS } from "@/lib/change-decision";
import { decideEventChangeRequestPartly, type TransitionState } from "../../actions";

const initialState: TransitionState = {};

/**
 * Hotfix 20 (Q&A #104): accept some of the fields in a change request and refuse the others,
 * each with the reason the Organiser will read. Only the accepted fields are applied.
 */
export function PartialChangeForm({
  eventRequestId,
  changeRequestId,
  fields,
}: {
  eventRequestId: string;
  changeRequestId: string;
  fields: string[];
}) {
  const id = useId();
  // Controlled: React clears uncontrolled fields after an action, losing every choice on a refusal.
  const [accepted, setAccepted] = useState<Record<string, boolean>>(() => Object.fromEntries(fields.map((field) => [field, true])));
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [state, formAction, isPending] = useActionState(
    decideEventChangeRequestPartly.bind(null, eventRequestId, changeRequestId, fields),
    initialState,
  );
  return (
    <details className="mt-4 border-t border-[#dce4e0] pt-4">
      <summary className="cursor-pointer text-sm font-semibold text-[#0f6b5b]">Accept some of these changes</summary>
      <form action={formAction} aria-busy={isPending} className="mt-3 space-y-4">
        <p className="text-sm text-[#526159]">
          Tick the changes to accept. Anything you leave unticked is not applied, and the Organiser is told why.
        </p>
        {fields.map((field) => {
          const reasonId = `${id}-${field}`;
          const error = state.fieldErrors?.[field];
          return (
            <fieldset key={field} className="rounded-lg border border-[#dce4e0] p-3">
              <legend className="px-1 text-sm font-semibold text-[#34463f]">{CHANGE_FIELD_LABELS[field] ?? field}</legend>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" name="accept" value={field} checked={accepted[field] ?? false} onChange={(event) => setAccepted((current) => ({ ...current, [field]: event.target.checked }))} disabled={isPending} />
                Accept this change
              </label>
              <label htmlFor={reasonId} className="mt-2 block text-sm text-[#526159]">
                Reason if not accepted
              </label>
              <input
                id={reasonId}
                name={`reason__${field}`}
                value={reasons[field] ?? ""}
                onChange={(event) => setReasons((current) => ({ ...current, [field]: event.target.value }))}
                maxLength={2000}
                disabled={isPending}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? `${reasonId}-error` : undefined}
                className="mt-1 min-h-11 w-full rounded-lg border border-[#cfd9d4] px-3 text-sm"
              />
              {error ? <p id={`${reasonId}-error`} className="mt-1 text-sm text-[#a23939]">{error}</p> : null}
            </fieldset>
          );
        })}
        <div>
          <label htmlFor={`${id}-note`} className="block text-sm font-semibold text-[#34463f]">Note to the Organiser (optional)</label>
          <textarea id={`${id}-note`} name="reason" rows={2} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} disabled={isPending} className="mt-1 w-full rounded-lg border border-[#cfd9d4] px-3 py-2 text-sm" />
        </div>
        {state.message ? <p role="alert" className="rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]">{state.message}</p> : null}
        <button type="submit" disabled={isPending} className="min-h-11 rounded-lg bg-[#0f6b5b] px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
          {isPending ? "Saving…" : "Apply the accepted changes"}
        </button>
      </form>
    </details>
  );
}
