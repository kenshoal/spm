import { getJson } from "./api";
import { formatDateTime } from "./event-requests";
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
    case "event_request_approved":
    case "event_request_rejected": {
      // SCRUM-36 AC1: the Organiser's outcome; a rejection carries the reason.
      const reason = notification.payload.reason;
      const approved = notification.event_type === "event_request_approved";
      return {
        message: `Your event request was ${approved ? "approved" : "rejected"}.`,
        href: id && `/event-requests/${id}/edit`,
        ...(typeof reason === "string" && reason.trim() ? { detail: reason.trim() } : {}),
      };
    }
    case "registration_confirmed": {
      // SCRUM-38 AC1: to the Attendee. There is no Attendee event page yet, so no link.
      const name = notification.payload.event_name;
      return {
        message: typeof name === "string" && name.trim() ? `You're registered for ${name.trim()}.` : "Your registration is confirmed.",
        href: null,
      };
    }
    case "registration_full": {
      // SCRUM-38 AC2: to the Organiser and the Coordinator, each linked to the page they can open.
      const name = notification.payload.event_name;
      const capacity = notification.payload.capacity;
      return {
        message: typeof name === "string" && name.trim() ? `Registration for ${name.trim()} is full.` : "Registration for your event is full.",
        href: id && (roles.includes("event_coordinator") ? `/coordination/requests/${id}` : `/event-requests/${id}/edit`),
        ...(typeof capacity === "number" ? { detail: `All ${capacity} places are taken.` } : {}),
      };
    }
    case "registration_opened":
    case "registration_closed": {
      // SCRUM-38 AC3: to the Organiser and the Coordinator, each linked to the page they can open.
      const name = notification.payload.event_name;
      const at = notification.payload.boundary_at;
      const verb = notification.event_type === "registration_opened" ? "opened" : "closed";
      return {
        message: typeof name === "string" && name.trim() ? `Registration for ${name.trim()} has ${verb}.` : `Registration for your event has ${verb}.`,
        href: id && (roles.includes("event_coordinator") ? `/coordination/requests/${id}` : `/event-requests/${id}/edit`),
        ...(typeof at === "string" && at ? { detail: formatDateTime(at) } : {}),
      };
    }
    case "event_cancelled": {
      // SCRUM-38 AC4: to registered Attendees. No Attendee event page yet, so no link.
      const name = notification.payload.event_name;
      return {
        message: typeof name === "string" && name.trim() ? `${name.trim()} has been cancelled.` : "An event you registered for has been cancelled.",
        href: null,
      };
    }
    case "event_changed": {
      // SCRUM-38 AC4: the dates of an event the Attendee registered for changed.
      const name = notification.payload.event_name;
      const dates = notification.payload.proposed_date_times;
      const shown = Array.isArray(dates)
        ? dates.filter((value): value is string => typeof value === "string").map(formatDateTime)
        : [];
      return {
        message: typeof name === "string" && name.trim() ? `The dates of ${name.trim()} have changed.` : "The dates of an event you registered for have changed.",
        href: null,
        ...(shown.length ? { detail: `New dates: ${shown.join("; ")}` } : {}),
      };
    }
    case "event_confirmed":
      // SCRUM-36 AC3: sent to the Organiser when the Safety Officer approves.
      return { message: "Your event is confirmed.", href: id && `/event-requests/${id}/edit` };
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
      // SCRUM-36 AC2: the Organiser gets the same notice. They cannot open the
      // Coordinator's view, so they see which venue was refused and their own page.
      const forOrganiser = roles.includes("event_organiser") && !roles.includes("event_coordinator");
      const detail = [
        forOrganiser ? text("venue_name") : null,
        reason && `Reason: ${reason}`,
        alternative && `Suggested alternative: ${alternative}`,
      ]
        .filter(Boolean)
        .join(". ");
      return {
        message: forOrganiser
          ? `A venue for your event${event ? ` ${event}` : ""} was rejected.`
          : `Your venue booking request${event ? ` for ${event}` : ""} was rejected.`,
        href: forOrganiser ? id && `/event-requests/${id}/edit` : href,
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
    case "waitlist_offered":
    case "waitlist_offer_expiring": {
      // SCRUM-24 AC5: to the Attendee. There is no Attendee event page yet,
      // so no link; an offer and its warning show the acceptance deadline.
      const name = notification.payload.event_name;
      const event = typeof name === "string" && name.trim() ? name.trim() : null;
      const expiring = notification.event_type === "waitlist_offer_expiring";
      const expires = notification.payload.expires_at;
      return {
        message: event
          ? expiring
            ? `Your place offer for ${event} expires soon.`
            : `You're offered a place at ${event}.`
          : expiring
            ? "Your place offer expires soon."
            : "You're offered a place at an event.",
        href: null,
        ...(typeof expires === "string" && expires
          ? { detail: `Accept by ${formatDateTime(expires)}.` }
          : {}),
      };
    }
    case "waitlist_offer_expired": {
      // SCRUM-24 AC5: the Attendee is back in the queue (D3).
      const name = notification.payload.event_name;
      const event = typeof name === "string" && name.trim() ? name.trim() : null;
      return {
        message: event
          ? `Your place offer for ${event} expired; you're back in the queue.`
          : "Your place offer expired; you're back in the queue.",
        href: null,
      };
    }
    case "waitlist_offer_revoked": {
      // SCRUM-24 AC5: a Coordinator chose someone else for that place (D9);
      // the holder keeps their position.
      const name = notification.payload.event_name;
      const event = typeof name === "string" && name.trim() ? name.trim() : null;
      return {
        message: event
          ? `The place offer for ${event} went to someone else; you keep your place in the queue.`
          : "The place offer went to someone else; you keep your place in the queue.",
        href: null,
      };
    }
    case "waitlist_closed": {
      // SCRUM-24 D11/D12: past the cut-off the list closes and a freed place
      // opens to normal registration.
      const name = notification.payload.event_name;
      const event = typeof name === "string" && name.trim() ? name.trim() : null;
      return {
        message: event
          ? `The waiting list for ${event} has closed.`
          : "The waiting list for your event has closed.",
        href: null,
        ...(event ? { detail: "Any place that frees up will open to registration." } : {}),
      };
    }
    case "waitlist_event_cancelled": {
      // SCRUM-24 D13: the event's cancellation releases every waiting-list place.
      const name = notification.payload.event_name;
      const event = typeof name === "string" && name.trim() ? name.trim() : null;
      return {
        message: event
          ? `${event} has been cancelled, so you're off its waiting list.`
          : "An event you were waiting for has been cancelled, so you're off its waiting list.",
        href: null,
      };
    }
    default:
      return { message: "There's an update on an event request.", href: null };
  }
}
