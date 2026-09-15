"use client";

import { useActionState, useState } from "react";
import {
  deleteEventRequest,
  type DeleteEventRequestState,
} from "./actions";

const initialState: DeleteEventRequestState = {};

export function DeleteDraftButton({
  eventRequestId,
  eventName,
}: {
  eventRequestId: string;
  eventName: string | null;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const deleteDraft = deleteEventRequest.bind(null, eventRequestId);
  const [state, formAction, isPending] = useActionState(
    deleteDraft,
    initialState,
  );

  const draftName = eventName?.trim() || "Untitled event request";

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="rounded-lg px-3 py-2 text-sm font-semibold text-[#a23939] transition hover:bg-[#fff0f0] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a23939] disabled:cursor-not-allowed disabled:opacity-60"
      >
        Delete draft
      </button>

      {isOpen ? (
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
            aria-labelledby={`delete-draft-title-${eventRequestId}`}
            aria-describedby={`delete-draft-description-${eventRequestId}`}
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-[0_24px_80px_rgba(18,39,32,0.28)]"
          >
            <div className="flex size-11 items-center justify-center rounded-full bg-[#fff0f0] text-xl text-[#a23939]">
              !
            </div>
            <h2
              id={`delete-draft-title-${eventRequestId}`}
              className="mt-4 text-xl font-bold text-[#1b2b25]"
            >
              Delete event draft?
            </h2>
            <p
              id={`delete-draft-description-${eventRequestId}`}
              className="mt-2 text-sm leading-6 text-[#68776f]"
            >
              <span className="font-semibold text-[#34473f]">{draftName}</span>{" "}
              will be permanently deleted. This action cannot be undone.
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
                Cancel
              </button>
              <form action={formAction}>
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded-lg bg-[#a23939] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#872e2e] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a23939] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isPending ? "Deleting…" : "Delete draft"}
                </button>
              </form>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
