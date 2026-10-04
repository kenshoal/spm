"use client";

import { useActionState } from "react";
import {
  respondToClarification,
  type ClarificationResponseState,
} from "../actions";

const initialState: ClarificationResponseState = {};

export function ClarificationResponseForm({
  eventRequestId,
}: {
  eventRequestId: string;
}) {
  const [state, formAction, pending] = useActionState(
    respondToClarification.bind(null, eventRequestId),
    initialState,
  );

  if (state.submitted) {
    return (
      <div role="status" className="rounded-xl border border-[#bcd9ce] bg-[#edf7f3] px-4 py-3 text-sm text-[#145c40]">
        Your response was sent. The assigned coordinator can now continue the review.
      </div>
    );
  }

  return (
    <form action={formAction} className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Respond to the coordinator</h2>
      <p className="mt-1 text-sm leading-6 text-[#718078]">
        Provide the requested clarification. Your response supplements the submitted request; its fields stay unchanged.
      </p>
      <label className="mt-5 block text-sm font-semibold text-[#34463f]">
        Clarification response
        <textarea
          name="response"
          required
          maxLength={2000}
          rows={5}
          aria-describedby={state.errors?.response ? "clarification-response-error" : undefined}
          className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3 text-sm outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]"
        />
      </label>
      {state.errors?.response ? (
        <p id="clarification-response-error" className="mt-1.5 text-sm text-[#a23939]">
          {state.errors.response}
        </p>
      ) : null}
      {state.message ? (
        <p role="alert" className="mt-3 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]">
          {state.message}
        </p>
      ) : null}
      <button type="submit" disabled={pending} className="mt-5 min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {pending ? "Sending response…" : "Send clarification response"}
      </button>
    </form>
  );
}
