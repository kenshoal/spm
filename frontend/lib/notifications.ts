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
    default:
      return { message: "There's an update on an event request.", href: null };
  }
}
