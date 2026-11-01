"use client";

import { useActionState } from "react";
import type { AttendeeActionState } from "./actions";

const initialState: AttendeeActionState = {};

// One attendee action as a button: it shows what the API refused, in words.
export function ActionButton({ label, pendingLabel, run, tone = "primary" }: {
  label: string;
  pendingLabel: string;
  run: () => Promise<AttendeeActionState>;
  tone?: "primary" | "quiet";
}) {
  const [state, action, pending] = useActionState(async () => run(), initialState);
  const style = tone === "primary"
    ? "bg-[#0f6b5b] text-white hover:bg-[#0b5b4d]"
    : "border border-[#cfd9d4] bg-white text-[#0f6b5b] hover:bg-[#f4f7f5]";
  return (
    <form action={action}>
      <button type="submit" disabled={pending} className={`min-h-11 rounded-xl px-4 text-sm font-bold disabled:opacity-60 ${style}`}>
        {pending ? pendingLabel : label}
      </button>
      {state.message ? <p role="alert" className="mt-2 text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}
