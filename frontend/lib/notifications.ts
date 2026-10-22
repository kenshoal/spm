import { getJson } from "./api";
import { timeRangeLabel } from "./venue-options";
import { reasonLabel, type BlockReason } from "./venue-block-options";
import { skillLabel } from "./technical-support-options";

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
// SCRUM-65: a notice carries its time range in minutes; notices sent before
// then only have slots, which are shown as they were.
function whenText(payload: Record<string, unknown>, startKey: string, endKey: string, slotsKey: string): string | null {
  const start = payload[startKey];
  const end = payload[endKey];
  if (typeof start === "number" && typeof end === "number") return timeRangeLabel(start, end);
  const slots = payload[slotsKey];
  return Array.isArray(slots) && slots.length ? slots.join(", ") : null;
}

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
    case "event_change_approved": {
      const reason = notification.payload.reason;
      return {
        message: "Your event change request was approved.",
        href: id && `/event-requests/${id}/edit`,
        ...(typeof reason === "string" && reason.trim() ? { detail: reason.trim() } : {}),
      };
    }
    case "event_change_rejected": {
      const reason = notification.payload.reason;
      return {
        message: "Your event change request was rejected.",
        href: id && `/event-requests/${id}/edit`,
        ...(typeof reason === "string" && reason.trim() ? { detail: reason.trim() } : {}),
      };
    }
    case "event_request_submitted":
      return { message: "Your event request was submitted.", href: id && `/event-requests/${id}/edit` };
    case "coordinator_assigned":
      return { message: "You've been assigned an event request.", href: id && `/coordination/requests/${id}` };
    case "coordinator_unassigned":
      // No link: the former coordinator can no longer open the request (SCRUM-62 AC4).
      return { message: "An event request you coordinated has been reassigned to another coordinator.", href: null };
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
        const where = [
          text("venue_name"),
          text("start_date") && text("end_date") && `${text("start_date")} to ${text("end_date")}`,
          whenText(notification.payload, "start_minute", "end_minute", "slots"),
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
      const category = text("reason_category");
      const reason = category
        ? [reasonLabel(category as BlockReason), text("reason_detail")].filter(Boolean).join(" — ")
        : null;
      const parts = [
        text("block_start_date") && text("block_end_date") && `Blocked ${text("block_start_date")} to ${text("block_end_date")}`,
        whenText(notification.payload, "block_start_minute", "block_end_minute", "block_slots"),
        reason,
      ].filter(Boolean);
      return {
        message: `${venue ?? "A venue"} has been blocked during your booking${event ? ` for ${event}` : ""}.`,
        href: id && `/coordination/requests/${id}`,
        detail: `${parts.join(" · ")}. Arrange an alternative venue or time.`,
      };
    }
    case "technical_support_assigned": {
      // SCRUM-19: sent to the assigned staff member. The payload carries the
      // skill tag, not the description, so the notice names the skill; there
      // is no link because a TSS assignments page is out of scope and the
      // coordination page is closed to technical_support.
      const skill = notification.payload.skill_tag;
      const event = notification.payload.event_name;
      const eventText =
        typeof event === "string" && event.trim() ? event.trim() : null;
      return {
        message: `You've been assigned as ${typeof skill === "string" ? skillLabel(skill) : "technical"} support${eventText ? ` for ${eventText}` : ""}.`,
        href: null,
      };
    }
    default:
      return { message: "There's an update on an event request.", href: null };
  }
}
