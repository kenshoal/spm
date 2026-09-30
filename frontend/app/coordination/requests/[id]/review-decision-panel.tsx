"use client";

import { useActionState, useState } from "react";
import {
  decideEventRequest,
  type ReviewDecision,
  type TransitionState,
} from "../../actions";

const initialState: TransitionState = {};

const decisions: Array<{
  value: ReviewDecision;
  label: string;
  title: string;
  description: string;
  reasonRequired: boolean;
}> = [
  {
    value: "Approved",
    label: "Approve request",
    title: "Approve this request?",
    description: "Approval records the review outcome so the request can proceed toward planning.",
    reasonRequired: false,
  },
  {
    value: "Changes Requested",
    label: "Request clarification",
    title: "Request clarification from the organiser",
    description: "Explain what the organiser must clarify before another review. Their response supplements the submitted request without changing its fields.",
    reasonRequired: true,
  },
  {
    value: "Rejected",
    label: "Reject request",
    title: "Reject this request?",
    description: "Give the organiser a clear reason. Rejection closes this request.",
    reasonRequired: true,
  },
];

export function ReviewDecisionPanel({ eventRequestId }: { eventRequestId: string }) {
  const [selected, setSelected] = useState<(typeof decisions)[number] | null>(null);
  const action = selected
    ? decideEventRequest.bind(null, eventRequestId, selected.value)
    : async () => initialState;
  const [state, formAction, isPending] = useActionState(action, initialState);

  return (
    <div className="mt-4">
      <div className="flex flex-wrap gap-3">
        {decisions.map((decision) => (
          <button
            key={decision.value}
            type="button"
            onClick={() => setSelected(decision)}
            className={
              decision.value === "Rejected"
                ? "rounded-lg border border-[#e4b6b0] bg-white px-4 py-2.5 text-sm font-semibold text-[#a23939] hover:bg-[#fff0f0]"
                : "rounded-lg bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0b5b4d]"
            }
          >
            {decision.label}
          </button>
        ))}
      </div>

      {selected ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[#15241f]/45 p-4">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-decision-title"
            className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-[0_24px_80px_rgba(18,39,32,0.28)]"
          >
            <h2 id="review-decision-title" className="text-xl font-bold text-[#1b2b25]">
              {selected.title}
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#68776f]">{selected.description}</p>
            <form action={formAction} className="mt-5">
              <label className="block text-sm font-semibold text-[#34463f]">
                Reason {selected.reasonRequired ? "(required)" : "(optional)"}
                <textarea
                  name="reason"
                  required={selected.reasonRequired}
                  maxLength={2000}
                  rows={5}
                  aria-describedby={state.errors?.reason ? "review-reason-error" : undefined}
                  className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3 text-sm outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]"
                />
              </label>
              {state.errors?.reason ? (
                <p id="review-reason-error" className="mt-1.5 text-sm text-[#a23939]">
                  {state.errors.reason}
                </p>
              ) : null}
              {state.message ? (
                <p role="alert" className="mt-3 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]">
                  {state.message}
                </p>
              ) : null}
              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  disabled={isPending}
                  onClick={() => setSelected(null)}
                  className="rounded-lg border border-[#ccd8d2] px-4 py-2.5 text-sm font-semibold text-[#34473f] hover:bg-[#f4f7f5] disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded-lg bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0b5b4d] disabled:opacity-60"
                >
                  {isPending ? "Saving decision…" : selected.label}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  );
}
