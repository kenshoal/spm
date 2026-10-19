"use client";

import { useActionState, useId, useState } from "react";
import type { Arrangement } from "@/lib/arrangement-reviews";
import { markArrangementReviewed, type ReviewClearState } from "./actions";

const initialState: ReviewClearState = {};

export function ClearReviewForm({ reviewId, arrangement }: { reviewId: string; arrangement: Arrangement }) {
  const [checked, setChecked] = useState(false);
  const checkboxId = useId();
  const [state, action, pending] = useActionState(markArrangementReviewed.bind(null, reviewId, arrangement), initialState);
  return (
    <form action={action} className="mt-4 space-y-3 border-t border-[#e3ebe7] pt-4">
      <p className="text-sm text-[#526159]">Check the referenced arrangement before recording your acknowledgement.</p>
      <label htmlFor={checkboxId} className="flex items-start gap-3 text-sm text-[#34463f]">
        <input id={checkboxId} name="reviewed" type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} disabled={pending} className="mt-1 size-4" />
        I have checked this arrangement against the recorded change
      </label>
      <button type="submit" disabled={!checked || pending} className="min-h-11 rounded-lg bg-[#0f6b5b] px-4 py-2 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:cursor-not-allowed disabled:opacity-60">
        {pending ? "Saving…" : "Mark reviewed"}
      </button>
      {state.message ? <p role="alert" className="text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
