// Client-safe tentative venue hold types and form rules (SCRUM-18): no import of
// ./api or ./auth, so the "use client" hold form can use them.
import { readTimeRange } from "./venue-options";

export type VenueHoldStatus = "active" | "released" | "converted" | "expired";

// A hold as venueService returns it.
export interface VenueHold {
  id: string;
  venue_id: string;
  event_request_id: string;
  start_date: string;
  end_date: string;
  start_minute: number;
  end_minute: number;
  expires_at: string;
  status: VenueHoldStatus;
  booking_request_id: string | null;
  placed_by: string;
  placed_at: string;
  closed_at: string | null;
}

export const HOLD_STATUS_LABELS: Record<VenueHoldStatus, string> = {
  active: "Held",
  released: "Released",
  converted: "Booked",
  expired: "Expired",
};

export interface PlaceHoldPayload {
  event_request_id: string;
  start_date: string;
  end_date: string;
  start_minute: number;
  end_minute: number;
  expires_at: string;
}

// Raw values echoed back after a failed submission.
export interface PlaceHoldValues {
  venue_id: string;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  expires_at: string;
}

export function readPlaceHoldValues(formData: FormData): PlaceHoldValues {
  const text = (key: string) => String(formData.get(key) ?? "").trim();
  return {
    venue_id: text("venue_id"),
    start_date: text("start_date"),
    end_date: text("end_date") || text("start_date"),
    start_time: text("start_time"),
    end_time: text("end_time"),
    expires_at: text("expires_at"),
  };
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const LOCAL_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
export const MAX_HOLD_DAYS = 7;

// The expiry field is a Singapore wall-clock time ("2026-11-01T18:00"), sent
// with its +08:00 offset so the API compares the same instant.
export function parsePlaceHoldForm(
  formData: FormData,
  eventRequestId: string,
  now: Date = new Date(),
): { venueId: string; payload: PlaceHoldPayload; errors: Record<string, string> } {
  const values = readPlaceHoldValues(formData);
  const times = readTimeRange(formData);
  const errors: Record<string, string> = { ...times.errors };
  if (!values.venue_id) errors.venue_id = "Choose a venue.";
  if (!DATE.test(values.start_date)) errors.start_date = "Choose a date.";
  else if (!DATE.test(values.end_date) || values.end_date < values.start_date) {
    errors.end_date = "The end date must be on or after the start date.";
  }
  const expiresAt = LOCAL_DATE_TIME.test(values.expires_at) ? `${values.expires_at}:00+08:00` : "";
  const expiry = expiresAt ? new Date(expiresAt).getTime() : Number.NaN;
  if (Number.isNaN(expiry)) errors.expires_at = "Choose when the hold expires.";
  else if (expiry <= now.getTime()) errors.expires_at = "The hold must expire in the future.";
  else if (expiry > now.getTime() + MAX_HOLD_DAYS * 24 * 60 * 60 * 1000) {
    errors.expires_at = "A hold can last at most 7 days.";
  }
  return {
    venueId: values.venue_id,
    payload: {
      event_request_id: eventRequestId,
      start_date: values.start_date,
      end_date: values.end_date,
      start_minute: times.start_minute,
      end_minute: times.end_minute,
      expires_at: expiresAt,
    },
    errors,
  };
}
