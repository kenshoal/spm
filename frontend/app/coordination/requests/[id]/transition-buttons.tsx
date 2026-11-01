"use client";

import { useActionState, useState } from "react";
import {
  cancelEventRequest,
  completeEventRequest,
  resumeEventRequestReview,
  sendForSafetyReview,
  startEventPlanning,
  startEventRequestReview,
  withdrawEventRequest,
  type TransitionState,
} from "../../actions";

type TransitionKind =
  | "review"
  | "planning"
  | "safety-review"
  | "resume-review"
  | "withdrawal"
  | "cancellation"
  | "completion";

const actions = {
  review: startEventRequestReview,
  planning: startEventPlanning,
  "safety-review": sendForSafetyReview,
  "resume-review": resumeEventRequestReview,
  withdrawal: withdrawEventRequest,
  cancellation: cancelEventRequest,
  completion: completeEventRequest,
} as const;

const buttons: Record<
  TransitionKind,
  { label: string; pending: string; destructive?: boolean }
> = {
  review: { label: "Start review", pending: "Starting review…" },
  planning: { label: "Start planning", pending: "Starting planning…" },
  "safety-review": { label: "Send for safety review", pending: "Sending…" },
  "resume-review": { label: "Continue review", pending: "Continuing review…" },
  withdrawal: { label: "Record withdrawal", pending: "Recording…", destructive: true },
  cancellation: {
    label: "Cancel event",
    pending: "Cancelling…",
    destructive: true,
  },
  completion: { label: "Mark complete", pending: "Marking complete…" },
};

const dialogs: Record<"withdrawal" | "cancellation" | "completion", { title: string; body: string }> = {
  withdrawal: {
    title: "Record the withdrawal of this request?",
    body: "Use this when the Event Organiser has asked you to withdraw the request. It stays on record as withdrawn, separate from cancelled and rejected, and the organiser is told.",
  },
  cancellation: {
    title: "Cancel this event?",
    body: "Cancelling stops all further coordination for this request. This cannot be undone.",
  },
  completion: {
    title: "Mark this event complete?",
    body: "This closes coordination for the request — the organiser will see the event as completed.",
  },
};

const initialState: TransitionState = {};

export function TransitionButton({
  eventRequestId,
  kind,
}: {
  eventRequestId: string;
  kind: TransitionKind;
}) {
  const config = buttons[kind];
  const [isOpen, setIsOpen] = useState(false);
  const transition = actions[kind].bind(null, eventRequestId);
  const [state, formAction, isPending] = useActionState(
    transition,
    initialState,
  );
  const dialog = kind === "withdrawal" || kind === "cancellation" || kind === "completion" ? dialogs[kind] : null;

  const buttonClass = config.destructive
    ? "rounded-lg border border-[#e4b6b0] bg-white px-4 py-2.5 text-sm font-semibold text-[#a23939] transition hover:bg-[#fff0f0] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a23939] disabled:cursor-not-allowed disabled:opacity-60"
    : "rounded-lg bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0b5b4d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b] disabled:cursor-not-allowed disabled:opacity-60";

  const submitButton = (
    <form action={formAction}>
      <button
        type="submit"
        disabled={isPending}
        className={
          config.destructive
            ? "rounded-lg bg-[#a23939] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#872e2e] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a23939] disabled:cursor-not-allowed disabled:opacity-60"
            : buttonClass
        }
      >
        {isPending ? config.pending : config.label}
      </button>
    </form>
  );

  return (
    <>
      {dialog ? (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          disabled={isPending}
          className={buttonClass}
        >
          {config.label}
        </button>
      ) : (
        submitButton
      )}

      {state.message && !(dialog && isOpen) ? (
        state.outstanding?.length ? (
          <div
            role="alert"
            className="mt-3 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]"
          >
            <p className="font-semibold">{state.message}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {state.outstanding.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        ) : (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]"
          >
            {state.message}
          </p>
        )
      ) : null}

      {dialog && isOpen ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-[#15241f]/45 p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !isPending) {
              setIsOpen(false);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape" && !isPending) setIsOpen(false);
          }}
        >
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={`transition-title-${kind}-${eventRequestId}`}
            aria-describedby={`transition-description-${kind}-${eventRequestId}`}
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-[0_24px_80px_rgba(18,39,32,0.28)]"
          >
            <div className={`flex size-11 items-center justify-center rounded-full text-xl ${config.destructive ? "bg-[#fff0f0] text-[#a23939]" : "bg-[#e3f2ea] text-[#145c40]"}`}>
              !
            </div>
            <h2
              id={`transition-title-${kind}-${eventRequestId}`}
              className="mt-4 text-xl font-bold text-[#1b2b25]"
            >
              {dialog.title}
            </h2>
            <p
              id={`transition-description-${kind}-${eventRequestId}`}
              className="mt-2 text-sm leading-6 text-[#68776f]"
            >
              {dialog.body}
            </p>

            {state.message ? (
              <p
                role="alert"
                className="mt-4 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]"
              >
                {state.message}
              </p>
            ) : null}

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                autoFocus
                disabled={isPending}
                onClick={() => setIsOpen(false)}
                className="rounded-lg border border-[#ccd8d2] px-4 py-2.5 text-sm font-semibold text-[#34473f] transition hover:bg-[#f4f7f5] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Keep as is
              </button>
              {submitButton}
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
