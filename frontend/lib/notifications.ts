import { getJson } from "./api";
import { reasonLabel, type BlockReason } from "./venue-block-options";

export interface AppNotification {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationSummary {
  message: string;
  href: string | null;
  // A line under the message, e.g. what the Coordinator needs clarified.
  detail?: string;
}

export const notificationApi = process.env.NOTIFICATION_API_URL ?? "http://127.0.0.1:8005";

export async function listNotifications(): Promise<AppNotification[]> {
  return (await getJson<AppNotification[]>(notificationApi, "/notifications")) ?? [];
}

// Each known type links to the view its recipient can open: the Organiser's own
// request page, or the assigned Coordinator's coordination page. A type added by
// another story still shows, with a generic message and no guessed link.
export function describeNotification(notification: AppNotification, roles: readonly string[] = []): NotificationSummary {
  const requestId = notification.payload.event_request_id;
  const id = typeof requestId === "string" && requestId ? encodeURIComponent(requestId) : null;
  switch (notification.event_type) {
    case "arrangement_needs_review": {
      const domain = notification.payload.arrangement;
      const label = domain === "venue_booking" ? "Venue booking" : domain === "equipment_reservation" ? "Equipment reservation" : "Arrangement";
      const staffRole = domain === "venue_booking" ? "venue_staff" : domain === "equipment_reservation" ? "technical_support" : null;
      const target = notification.payload.arrangement_id;
      const reason = notification.payload.reason;
      // Use verified capabilities and constructed internal paths, never payload.href.
      const href = staffRole && roles.includes(staffRole)
        ? `/arrangement-reviews?arrangement=${domain}`
        : roles.includes("event_coordinator") && id ? `/coordination/requests/${id}` : null;
      return {
        message: `${label} needs review.`,
        href,
        detail: [typeof target === "string" && target ? `Arrangement: ${target}` : null,
          typeof reason === "string" && reason.trim() ? reason : null].filter(Boolean).join(" · "),
      };
    }
    case "event_request_submitted":
      return { message: "Your event request was submitted.", href: id && `/event-requests/${id}/edit` };
    case "coordinator_assigned":
      return { message: "You've been assigned an event request.", href: id && `/coordination/requests/${id}` };
    case "clarification_requested": {
      // The Organiser answers on the same page they edit and track the request from.
      const reason = notification.payload.reason;
      return {
        message: "A coordinator has asked for clarification on your event request.",
        href: id && `/event-requests/${id}/edit`,
        ...(typeof reason === "string" && reason.trim() ? { detail: reason.trim() } : {}),
      };
    }
    case "venue_booking_approved":
    case "venue_booking_rejected": {
      // SCRUM-15: sent to the Coordinator who requested the booking, so it
      // links to their coordination view of the event.
      const text = (key: string) => {
        const value = notification.payload[key];
        return typeof value === "string" && value.trim() ? value.trim() : null;
      };
      const event = text("event_name");
      const href = id && `/coordination/requests/${id}`;
      if (notification.event_type === "venue_booking_approved") {
        const slots = notification.payload.slots;
        const where = [
          text("venue_name"),
          text("start_date") && text("end_date") && `${text("start_date")} to ${text("end_date")}`,
          Array.isArray(slots) && slots.length ? slots.join(", ") : null,
        ].filter(Boolean);
        return {
          message: `Your venue booking${event ? ` for ${event}` : ""} was approved.`,
          href,
          ...(where.length ? { detail: where.join(" · ") } : {}),
        };
      }
      const reason = text("decision_reason");
      const alternative = text("suggested_alternative");
      const detail = [reason && `Reason: ${reason}`, alternative && `Suggested alternative: ${alternative}`]
        .filter(Boolean)
        .join(". ");
      return {
        message: `Your venue booking request${event ? ` for ${event}` : ""} was rejected.`,
        href,
        ...(detail ? { detail } : {}),
      };
    }
    case "venue_block_affects_booking": {
      // SCRUM-23 AC3: a new block overlaps the Coordinator's approved booking.
      const text = (key: string) => {
        const value = notification.payload[key];
        return typeof value === "string" && value.trim() ? value.trim() : null;
      };
      const venue = text("venue_name");
      const event = text("event_name");
      const slots = notification.payload.block_slots;
      const category = text("reason_category");
      const reason = category
        ? [reasonLabel(category as BlockReason), text("reason_detail")].filter(Boolean).join(" — ")
        : null;
      const parts = [
        text("block_start_date") && text("block_end_date") && `Blocked ${text("block_start_date")} to ${text("block_end_date")}`,
        Array.isArray(slots) && slots.length ? slots.join(", ") : null,
        reason,
      ].filter(Boolean);
      return {
        message: `${venue ?? "A venue"} has been blocked during your booking${event ? ` for ${event}` : ""}.`,
        href: id && `/coordination/requests/${id}`,
        detail: `${parts.join(" · ")}. Arrange an alternative venue or time.`,
      };
    }
    default:
      return { message: "There's an update on an event request.", href: null };
  }
}
