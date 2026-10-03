"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireAccessToken, requireRole } from "@/lib/auth";

export interface TransitionState {
  message?: string;
  errors?: { reason?: string };
}

export type ReviewDecision = "Approved" | "Changes Requested" | "Rejected";

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

async function transition(
  eventRequestId: string,
  path: "review" | "resume-review" | "cancellation" | "completion",
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

export async function startEventRequestReview(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "review");
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
