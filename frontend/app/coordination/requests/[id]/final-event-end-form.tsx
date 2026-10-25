"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { finalEndInput } from "@/lib/event-final-end";
import { setEventFinalEnd, type FinalEndState } from "../../actions";

/** Record an explicit end; no date, venue or equipment time is used as a guess. */
export function FinalEventEndForm({ eventRequestId, finalEventEndAt }: {
  eventRequestId: string;
  finalEventEndAt?: string | null;
}) {
  const router = useRouter();
  const [value, setValue] = useState(() => finalEndInput(finalEventEndAt));
  const [state, setState] = useState<FinalEndState>({});
  const [pending, setPending] = useState(false);
  const [, startTransition] = useTransition();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const data = new FormData(event.currentTarget);
    setPending(true);
    startTransition(async () => {
      try {
        const result = await setEventFinalEnd(eventRequestId, state, data);
        setState(result);
        if (result.saved) router.refresh();
      } finally {
        setPending(false);
      }
    });
  }

  return (
    <section aria-label="Final event end" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Final event end</h2>
      <p className="mt-2 text-sm text-[#526159]">Record the final end before confirmation. A Confirmed event can complete automatically only after seven full days have elapsed. Rescheduling event dates clears this end so it must be recorded again.</p>
      <form onSubmit={submit} aria-busy={pending} className="mt-4 space-y-3">
        <label className="block text-sm font-semibold">Final event end (Singapore time)
          <input type="datetime-local" name="final_event_end_at" required value={value} onChange={(event) => setValue(event.target.value)} disabled={pending} className="mt-1 block w-full rounded-lg border border-[#cfd9d4] px-3 py-2 disabled:opacity-60" />
        </label>
        {state.message ? <p role="alert" className="text-sm text-[#a23939]">{state.message}</p> : null}
        {state.saved ? <p role="status" className="text-sm text-[#145c40]">Final event end saved.</p> : null}
        <button type="submit" disabled={pending} className="min-h-11 rounded-lg bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">{pending ? "Saving final event end…" : "Save final event end"}</button>
      </form>
    </section>
  );
}
