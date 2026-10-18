"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireAccessToken, requireRole } from "@/lib/auth";

export interface TransitionState {
  message?: string;
  errors?: { reason?: string };
  // SCRUM-58 AC3: what still blocks sending for safety review, one line each.
  outstanding?: string[];
}

export type ReviewDecision = "Approved" | "Changes Requested" | "Rejected";
export type ChangeDecision = "Approved" | "Rejected";

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

async function transition(
  eventRequestId: string,
  path: "review" | "planning" | "safety-review" | "resume-review" | "cancellation" | "completion",
): Promise<TransitionState> {
  await requireRole("event_coordinator");
  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/${path}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      },
    );
  } catch {
    return { message: "That could not be done. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (response.status === 409) {
    // Only the safety-review refusal carries a list; any other 409 is a stale status.
    const outstanding = await outstandingMessages(response);
    if (outstanding.length > 0) {
      return { message: "This event isn't ready for safety review yet.", outstanding };
    }
  }
  if (!response.ok) {
    return {
      message:
        response.status === 403
          ? "Only the coordinator currently assigned to this request can do that."
          : response.status === 409
            ? "This request's status has already changed. Refresh the page to see where it stands."
            : "That could not be done. Please try again.",
    };
  }
  revalidatePath("/coordination/requests");
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath("/event-requests");
  return {};
}

async function outstandingMessages(response: Response): Promise<string[]> {
  try {
    const body = (await response.json()) as { outstanding?: unknown };
    if (!Array.isArray(body.outstanding)) return [];
    return body.outstanding
      .map((item) => String((item as { message?: unknown }).message ?? "").trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

export async function startEventRequestReview(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "review");
}

export async function startEventPlanning(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "planning");
}

export async function sendForSafetyReview(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "safety-review");
}

export async function resumeEventRequestReview(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "resume-review");
}

export async function cancelEventRequest(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "cancellation");
}

export async function completeEventRequest(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "completion");
}

export async function decideEventRequest(
  eventRequestId: string,
  decision: ReviewDecision,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  await requireRole("event_coordinator");
  const reason = String(formData.get("reason") ?? "").trim();
  if ((decision === "Changes Requested" || decision === "Rejected") && !reason) {
    return {
      message: "Explain the decision before continuing.",
      errors: { reason: "Enter a reason for the organiser." },
    };
  }

  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/decision`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ decision, reason: reason || null }),
      },
    );
  } catch {
    return { message: "The decision could not be recorded. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 403
          ? "Only the coordinator currently assigned to this request can decide it."
          : response.status === 409
            ? "This request is no longer under review. Refresh the page to see where it stands."
            : response.status === 422
              ? "Check the decision details and try again."
              : "The decision could not be recorded. Please try again.",
    };
  }

  revalidatePath("/coordination/requests");
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath("/event-requests");
  return {};
}

export async function decideEventChangeRequest(
  eventRequestId: string,
  changeRequestId: string,
  decision: ChangeDecision,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  await requireRole("event_coordinator");
  const reason = String(formData.get("reason") ?? "").trim();
  if (decision === "Rejected" && !reason) {
    return { message: "Explain why the change is rejected.", errors: { reason: "Enter a reason for the organiser." } };
  }
  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/change-requests/${encodeURIComponent(changeRequestId)}/decision`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ decision, reason: reason || null }),
      },
    );
  } catch {
    return { message: "The change decision could not be recorded. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    if (response.status === 409) {
      const body = await response.json().catch(() => null);
      if (body?.detail?.code === "CHANGE_DECISIONS_UNAVAILABLE") {
        return { message: "Approval and rejection are unavailable until arrangement review is supported." };
      }
    }
    return {
      message: response.status === 403
        ? "Only the coordinator currently assigned to this request can decide the change."
        : response.status === 409
          ? "This change is already decided or the event plan has changed. Refresh before deciding."
          : response.status === 422
            ? "Check the decision details and try again."
            : "The change decision could not be recorded. Please try again.",
    };
  }
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  revalidatePath("/event-requests");
  return {};
}
