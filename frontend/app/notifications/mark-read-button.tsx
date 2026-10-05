"use client";

import { useActionState } from "react";
import { markNotificationRead, type MarkReadState } from "./actions";

const initialState: MarkReadState = {};

export function MarkReadButton({ notificationId }: { notificationId: string }) {
  const [state, formAction, isPending] = useActionState(
    markNotificationRead.bind(null, notificationId),
    initialState,
  );
  return (
    <form action={formAction} className="flex flex-wrap items-center gap-3">
      <button
        type="submit"
        disabled={isPending}
        className="min-h-10 rounded-xl border border-[#cfd9d4] bg-white px-3.5 text-sm font-semibold text-[#0f6b5b] hover:bg-[#f1f7f4] disabled:opacity-60"
      >
        {isPending ? "Saving…" : "Mark as read"}
      </button>
      {state.message ? (
        <p role="alert" className="rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]">
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
