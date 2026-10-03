"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireAccessToken, requireRole } from "@/lib/auth";

export interface TransitionState {
  message?: string;
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

async function transition(
  eventRequestId: string,
  path: "review" | "cancellation" | "completion",
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
