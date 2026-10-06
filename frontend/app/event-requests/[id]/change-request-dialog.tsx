"use client";

import { useRef } from "react";
import { ChangeRequestForm } from "./change-request-form";

export function ChangeRequestDialog({ eventRequestId }: { eventRequestId: string }) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  return (
    <>
      <button
        type="button"
        onClick={() => dialogRef.current?.showModal()}
        className="inline-flex min-h-10 items-center justify-center rounded-xl bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#0b5b4d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b]"
      >
        Request a change
      </button>
      <dialog
        ref={dialogRef}
        aria-labelledby="request-change-title"
        className="fixed inset-0 m-auto max-h-[90vh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto rounded-2xl border-0 bg-white p-0 shadow-[0_24px_80px_rgba(18,39,32,0.28)] backdrop:bg-[#15241f]/55"
      >
        <button
          type="button"
          onClick={() => dialogRef.current?.close()}
          className="absolute right-5 top-5 rounded-lg px-3 py-2 text-sm font-semibold text-[#526159] hover:bg-[#eef3f0] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b]"
        >
          Close
        </button>
        <ChangeRequestForm eventRequestId={eventRequestId} />
      </dialog>
    </>
  );
}
