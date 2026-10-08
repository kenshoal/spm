import { getJson } from "./api";

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
export function describeNotification(notification: AppNotification): NotificationSummary {
  const requestId = notification.payload.event_request_id;
  const id = typeof requestId === "string" && requestId ? encodeURIComponent(requestId) : null;
  switch (notification.event_type) {
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
    default:
      return { message: "There's an update on an event request.", href: null };
  }
}
