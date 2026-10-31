"use client";

import { useActionState } from "react";
import { END_TIMES, START_TIMES, timeLabel } from "@/lib/venue-options";
import {
  convertVenueHold,
  placeVenueHold,
  releaseVenueHold,
  type HoldActionState,
  type PlaceHoldState,
} from "./venue-hold-actions";

const inputClass = "mt-1 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 py-2 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function FieldError({ message }: { message?: string }) {
  return message ? <span className="mt-1 block text-sm font-normal text-[#a23939]">{message}</span> : null;
}

// Holds a venue for this event while it is being finalised (SCRUM-18). The
// expiry is Singapore time, at most 7 days ahead.
export function PlaceHoldForm({ eventRequestId, venues }: { eventRequestId: string; venues: { id: string; name: string }[] }) {
  const [state, formAction, isPending] = useActionState(placeVenueHold.bind(null, eventRequestId), {} as PlaceHoldState);
  const errors = state.errors ?? {};
  const values = state.values;
  return (
    <form action={formAction} noValidate className="mt-4 grid gap-3 rounded-xl border border-[#e1e7e4] p-4 sm:grid-cols-2">
      <label className={labelClass}>
        Venue
        <select name="venue_id" defaultValue={values?.venue_id ?? ""} className={inputClass}>
          <option value="">Choose a venue</option>
          {venues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name}</option>)}
        </select>
        <FieldError message={errors.venue_id} />
      </label>
      <label className={labelClass}>
        Hold expires (Singapore time)
        <input name="expires_at" type="datetime-local" defaultValue={values?.expires_at} className={inputClass} />
        <FieldError message={errors.expires_at} />
      </label>
      <label className={labelClass}>
        Start date
        <input name="start_date" type="date" defaultValue={values?.start_date} className={inputClass} />
        <FieldError message={errors.start_date} />
      </label>
      <label className={labelClass}>
        End date
        <input name="end_date" type="date" defaultValue={values?.end_date} className={inputClass} />
        <FieldError message={errors.end_date} />
      </label>
      <label className={labelClass}>
        Start time
        <select name="start_time" defaultValue={values?.start_time ?? ""} className={inputClass}>
          <option value="">Choose</option>
          {START_TIMES.map((minute) => <option key={minute} value={timeLabel(minute)}>{timeLabel(minute)}</option>)}
        </select>
        <FieldError message={errors.start_time} />
      </label>
      <label className={labelClass}>
        End time
        <select name="end_time" defaultValue={values?.end_time ?? ""} className={inputClass}>
          <option value="">Choose</option>
          {END_TIMES.map((minute) => <option key={minute} value={timeLabel(minute)}>{timeLabel(minute)}</option>)}
        </select>
        <FieldError message={errors.end_time} />
      </label>
      <div className="sm:col-span-2">
        <button type="submit" disabled={isPending} className="min-h-10 rounded-xl bg-[#0f6b5b] px-4 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
          Hold venue
        </button>
        {state.message ? <p role="alert" className="mt-2 text-sm text-[#a23939]">{state.message}</p> : null}
      </div>
    </form>
  );
}

function HoldButton({
  action,
  holdId,
  eventRequestId,
  label,
  ariaLabel,
  confirmText,
}: {
  action: (state: HoldActionState, formData: FormData) => Promise<HoldActionState>;
  holdId: string;
  eventRequestId: string;
  label: string;
  ariaLabel: string;
  confirmText: string;
}) {
  const [state, formAction, isPending] = useActionState(action, {} as HoldActionState);
  return (
    <form
      action={formAction}
      onSubmit={(event) => {
        if (!window.confirm(confirmText)) event.preventDefault();
      }}
    >
      <input type="hidden" name="hold_id" value={holdId} />
      <input type="hidden" name="event_request_id" value={eventRequestId} />
      <button
        type="submit"
        disabled={isPending}
        aria-label={ariaLabel}
        className="min-h-9 rounded-lg border border-[#cfd9d4] px-3 text-sm font-semibold text-[#273832] hover:bg-[#f2f6f4] disabled:opacity-60"
      >
        {label}
      </button>
      {state.message ? <p role="alert" className="mt-2 text-sm text-[#a23939]">{state.message}</p> : null}
    </form>
  );
}

export function HoldActions({ holdId, eventRequestId, venueName, canConvert }: {
  holdId: string;
  eventRequestId: string;
  venueName: string;
  canConvert: boolean;
}) {
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {canConvert ? (
        <HoldButton
          action={convertVenueHold}
          holdId={holdId}
          eventRequestId={eventRequestId}
          label="Request booking"
          ariaLabel={`Request booking for hold at ${venueName}`}
          confirmText={`Send a booking request for the held time at ${venueName}? The hold keeps the time until Venue Staff decide.`}
        />
      ) : null}
      <HoldButton
        action={releaseVenueHold}
        holdId={holdId}
        eventRequestId={eventRequestId}
        label="Release"
        ariaLabel={`Release hold at ${venueName}`}
        confirmText={`Release the hold at ${venueName}? The time becomes available to others straight away.`}
      />
    </div>
  );
}
