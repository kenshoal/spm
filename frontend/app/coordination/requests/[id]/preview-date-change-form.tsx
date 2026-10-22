"use client";

import { useActionState } from "react";
import { previewEventChangeDatePlan, type PreviewDateChangeState } from "../../actions";

const initialState: PreviewDateChangeState = {};

function formatMinute(value: number): string {
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

/** Load an advisory snapshot on demand; no approval or resource write is offered. */
export function PreviewDateChangeForm({
  eventRequestId,
  changeRequestId,
}: {
  eventRequestId: string;
  changeRequestId: string;
}) {
  const [state, formAction, isPending] = useActionState(
    previewEventChangeDatePlan.bind(null, eventRequestId, changeRequestId),
    initialState,
  );

  return (
    <form action={formAction} aria-busy={isPending} className="mt-4">
      <p className="text-sm text-[#68776f]">Preview only. No changes have been made. Use the complete booking plan to request date approval.</p>
      <button
        type="submit"
        disabled={isPending}
        className="mt-3 rounded-lg border border-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-[#0f6b5b] hover:bg-[#edf5f1] disabled:opacity-60"
      >
        {isPending ? "Loading preview…" : "Preview date changes"}
      </button>
      {state.message ? <p role="alert" className="mt-3 rounded-lg bg-[#fff0f0] px-3 py-2 text-sm text-[#a23939]">{state.message}</p> : null}
      {!isPending && state.plan ? (
        <section aria-label="Date change preview" className="mt-3 rounded-lg border border-[#dce4e0] p-3 text-sm">
          <p className="text-[#68776f]">These dates are an advisory snapshot. Availability has not been checked.</p>
          {state.plan.bookings.length === 0 ? (
            <p className="mt-2">No pending or approved venue bookings to move.</p>
          ) : (
            <ul className="mt-2 space-y-3">
              {state.plan.bookings.map((booking) => (
                <li key={booking.booking_id} className="break-words">
                  <p><strong>Venue:</strong> {booking.venue_id}</p>
                  <p><strong>Booking:</strong> {booking.booking_id} ({booking.status})</p>
                  <p><strong>Current:</strong> <time dateTime={booking.current_start_date}>{booking.current_start_date}</time> to <time dateTime={booking.current_end_date}>{booking.current_end_date}</time></p>
                  <p><strong>Proposed:</strong> <time dateTime={booking.proposed_start_date}>{booking.proposed_start_date}</time> to <time dateTime={booking.proposed_end_date}>{booking.proposed_end_date}</time></p>
                  <p><strong>Time retained:</strong> {formatMinute(booking.start_minute)}–{formatMinute(booking.end_minute)} (Singapore time)</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </form>
  );
}
