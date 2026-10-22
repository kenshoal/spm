"use client";

import { useActionState, useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import type { EventChangeBookingPlan, EventChangeBookingPlanItem } from "@/lib/event-requests";
import { formatBookingMinute } from "@/lib/booking-plan-format";
import { decideEventChangeRequest, loadEventChangeBookingPlan, type BookingPlanState, type TransitionState } from "../../actions";

const startMinutes = Array.from({ length: 68 }, (_, index) => 420 + index * 15);
const endMinutes = Array.from({ length: 68 }, (_, index) => 435 + index * 15);
const conflictLabels: Record<string, string> = {
  venue_unavailable: "Venue unavailable",
  active_block: "Overlaps an active venue block",
  setup_outside_window: "Setup falls outside booking hours",
  turnaround_outside_window: "Turnaround falls outside booking hours",
  booking_conflict: "Overlaps another booking in the complete plan or at this venue",
};

/** The complete snapshot is advisory; SQL rechecks membership and every conflict. */
export function DateChangeApprovalForm({ eventRequestId, changeRequestId }: { eventRequestId: string; changeRequestId: string }) {
  const router = useRouter();
  const [context, setContext] = useState<EventChangeBookingPlan>();
  const [ranges, setRanges] = useState<EventChangeBookingPlanItem[]>([]);
  const [saved, setSaved] = useState(false);
  const [loadState, loadAction, loading] = useActionState(async (previous: BookingPlanState, data: FormData) => {
    setContext(undefined);
    const result = await loadEventChangeBookingPlan(eventRequestId, changeRequestId, previous, data);
    if (result.plan) {
      setContext(result.plan);
      setRanges((result.plan.automatic_plan ?? result.plan.bookings).map((row) => ({
        booking_id: row.booking_id, start_date: row.start_date, end_date: row.end_date,
        start_minute: row.start_minute, end_minute: row.end_minute,
      })));
    }
    return result;
  }, {});
  const [state, setState] = useState<TransitionState>({});
  const [approving, setApproving] = useState(false);
  const [, startApproving] = useTransition();

  // Submit explicitly so an unsuccessful action cannot reset selected ranges.
  function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (approving || saved) return;
    setApproving(true);
    startApproving(async () => {
      try {
        const result = await decideEventChangeRequest(eventRequestId, changeRequestId, "Approved", state, data);
        setState(result);
        if (!result.message && !result.errors && !result.bookingConflicts?.length && !result.outstanding?.length) {
          setSaved(true);
          router.refresh();
        }
      } finally {
        setApproving(false);
      }
    });
  }

  function editRange(index: number, field: "start_date" | "end_date" | "start_minute" | "end_minute", value: string) {
    setRanges((current) => current.map((row, position) => position === index
      ? { ...row, [field]: field.endsWith("minute") ? Number(value) : value } : row));
  }

  return (
    <div className="mt-4 space-y-4">
      <form action={loadAction}>
        <button type="submit" disabled={loading || approving || saved} className="min-h-11 rounded-lg border border-[#0f6b5b] px-4 py-2 text-sm font-semibold text-[#0f6b5b] disabled:opacity-60">
          {loading ? "Loading booking plan…" : "Review booking plan"}
        </button>
        {loadState.message ? <p role="alert" className="mt-3 text-sm text-[#a23939]">{loadState.message}</p> : null}
      </form>
      {context ? (
        <section aria-label="Booking plan" className="rounded-xl border border-[#dce4e0] p-4">
          <h3 className="font-bold">Booking plan</h3>
          <p className="mt-2 text-sm text-[#526159]">Review every pending and approved booking. Availability is checked when you approve; one conflict refuses the whole change. Event dates have no end time, so each booking end is an explicit choice.</p>
          {context.automatic_plan === null ? <p className="mt-2 text-sm">Automatic date mapping is unavailable. Check these booking ranges against the proposed event dates and times before approving. Enter replacement dates and times for every booking below.</p> : <p className="mt-2 text-sm">The initial ranges follow the uniform event-date shift. Review them before approving.</p>}
          <form onSubmit={approve} className="mt-4 space-y-4" aria-busy={approving}>
            <input type="hidden" name="booking_plan" value={JSON.stringify(ranges)} />
            {ranges.length === 0 ? <p>No pending or approved venue bookings to move.</p> : ranges.map((row, index) => (
              <fieldset key={row.booking_id} disabled={approving || saved} className="rounded-lg border border-[#dce4e0] p-3">
                <legend className="break-all px-1 text-sm font-semibold">Booking {row.booking_id} ({context.bookings.find((booking) => booking.booking_id === row.booking_id)?.status})</legend>
                <p className="mb-3 break-all text-xs text-[#68776f]">Venue: {context.bookings.find((booking) => booking.booking_id === row.booking_id)?.venue_id}</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-sm">Start date<input type="date" required value={row.start_date} onChange={(event) => editRange(index, "start_date", event.target.value)} className="mt-1 w-full rounded border border-[#cfd9d4] p-2" /></label>
                  <label className="text-sm">End date<input type="date" required value={row.end_date} onChange={(event) => editRange(index, "end_date", event.target.value)} className="mt-1 w-full rounded border border-[#cfd9d4] p-2" /></label>
                  <label className="text-sm">Start time (Singapore)<select value={row.start_minute} onChange={(event) => editRange(index, "start_minute", event.target.value)} className="mt-1 w-full rounded border border-[#cfd9d4] p-2">{startMinutes.map((minute) => <option key={minute} value={minute}>{formatBookingMinute(minute)}</option>)}</select></label>
                  <label className="text-sm">End time (Singapore)<select value={row.end_minute} onChange={(event) => editRange(index, "end_minute", event.target.value)} className="mt-1 w-full rounded border border-[#cfd9d4] p-2">{endMinutes.map((minute) => <option key={minute} value={minute}>{formatBookingMinute(minute)}</option>)}</select></label>
                </div>
              </fieldset>
            ))}
            <label className="block text-sm">Coordinator note (optional)<textarea name="reason" maxLength={2000} disabled={approving || saved} rows={2} className="mt-1 w-full rounded border border-[#cfd9d4] p-2" /></label>
            {state.message || state.bookingConflicts?.length ? <div role="alert" className="rounded-lg bg-[#fff0f0] p-3 text-sm text-[#a23939]">
              {state.message}
              {state.bookingConflicts?.map((conflict) => <p key={conflict.booking_id} className="mt-2 break-words">Booking {conflict.booking_id}: {conflict.refusal_codes.map((code) => conflictLabels[code] ?? "Booking range unavailable").join("; ")}</p>)}
            </div> : null}
            {saved ? <p role="status">Change approved. Refreshing the saved outcome…</p> : null}
            <button type="submit" disabled={approving || saved} className="min-h-11 rounded-lg bg-[#0f6b5b] px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">{approving ? "Approving…" : "Approve change"}</button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
