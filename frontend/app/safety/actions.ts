"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { parseSafetyDecisionForm } from "@/lib/safety";

export interface SafetyDecisionState {
  message?: string;
  errors?: Record<string, string>;
  reason?: string;
}

const eventRequestApiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";
const retryMessage = "The decision could not be saved. Please try again.";
const failureMessages: Record<number, string> = {
  403: "Only a Safety Officer can record a safety decision.",
  404: "This event no longer exists.",
  422: "The decision was not accepted. Check the reason and the arrangements you ticked.",
};

async function readBody(response: Response): Promise<{ detail?: unknown; outstanding?: unknown } | null> {
  try {
    return (await response.json()) as { detail?: unknown; outstanding?: unknown };
  } catch {
    return null;
  }
}

export async function decideSafety(
  eventRequestId: string,
  previousState: SafetyDecisionState,
  formData: FormData,
): Promise<SafetyDecisionState> {
  void previousState;
  const reason = String(formData.get("reason") ?? "");
  const { payload, errors } = parseSafetyDecisionForm(formData);
  if (Object.keys(errors).length) return { message: "Check the highlighted fields.", errors, reason };

  await requireRole("safety_officer");
  let response: Response;
  try {
    response = await sendJson(
      eventRequestApiUrl,
      `/event-requests/${encodeURIComponent(eventRequestId)}/safety-decision`,
      "POST",
      payload,
    );
  } catch {
    return { message: retryMessage, reason };
  }
  // redirect() throws, so it stays outside the try above.
  if (response.status === 401) redirect("/auth");
  if (response.status === 409) {
    // The outstanding list comes from increment 2b (0045/0047, after PR #63):
    // review flags and readiness items. Until then a 409 only means the event
    // is no longer waiting.
    const outstanding = (await readBody(response))?.outstanding;
    if (Array.isArray(outstanding) && outstanding.length > 0) {
      const reasons = outstanding.map((item) => String((item as { message?: unknown }).message ?? ""));
      return { message: ["Approval refused.", ...reasons].join(" "), reason };
    }
    return { message: "This event is no longer waiting for a safety check. Refresh the queue." };
  }
  if (!response.ok) return { message: failureMessages[response.status] ?? retryMessage, reason };
  revalidatePath("/safety");
  redirect(`/safety?decided=${payload.decision}`);
}
