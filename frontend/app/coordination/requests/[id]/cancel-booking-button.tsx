"use client";

import { useActionState } from "react";
import { cancelVenueBooking, type CancelBookingState } from "./venue-booking-actions";

const initialState: CancelBookingState = {};

export function CancelBookingButton({
  bookingId,
  eventRequestId,
  venueName,
}: {
  bookingId: string;
  eventRequestId: string;
  venueName: string;
}) {
  const [state, formAction, isPending] = useActionState(cancelVenueBooking, initialState);
  return (
    <form
      action={formAction}
      onSubmit={(event) => {
        if (!window.confirm(`Cancel the booking at ${venueName}? The event's other bookings are not affected.`)) {
          event.preventDefault();
        }
      }}
    >
      <input type="hidden" name="booking_id" value={bookingId} />
      <input type="hidden" name="event_request_id" value={eventRequestId} />
      <button
        type="submit"
        disabled={isPending}
        aria-label={`Cancel booking at ${venueName}`}
        className="min-h-9 rounded-lg border border-[#d9b8ae] px-3 text-sm font-semibold text-[#8a3b25] hover:bg-[#fff3ee] disabled:opacity-60"
      >
        Cancel booking
      </button>
      {state.message ? <p role="alert" className="mt-2 text-sm text-[#a23939]">{state.message}</p> : null}
    </form>
  );
}
