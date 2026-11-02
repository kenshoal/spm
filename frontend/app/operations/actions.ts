"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { readDetail, sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";

export interface AssignState {
  message?: string;
  assigned?: boolean;
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

export async function assignCoordinator(
  eventRequestId: string,
  previousState: AssignState,
  formData: FormData,
): Promise<AssignState> {
  void previousState;
  const coordinatorId = String(formData.get("coordinator_id") ?? "").trim();
  if (!coordinatorId) return { message: "Choose a coordinator to assign." };
  const currentCoordinatorId = String(formData.get("current_coordinator_id") ?? "").trim();

  await requireRole("event_operations_manager");
  let response: Response;
  try {
    response = await sendJson(
      apiUrl,
      `/event-requests/${encodeURIComponent(eventRequestId)}/coordinator`,
      "POST",
      { coordinator_id: coordinatorId, expected_coordinator_id: currentCoordinatorId || null },
    );
  } catch {
    return { message: "The coordinator could not be assigned. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    if (response.status === 409) {
      return { message: (await readDetail(response)) ?? "This request can no longer be assigned. Refresh the page." };
    }
    return {
      message:
        response.status === 403
          ? "Only an Event Coordinator Lead can assign coordinators."
          : response.status === 404
            ? "This request no longer exists. Refresh the page."
            : "The coordinator could not be assigned. Please try again.",
    };
  }
  revalidatePath("/operations/assignments");
  return { assigned: true, message: currentCoordinatorId ? "Coordinator reassigned." : "Coordinator assigned." };
}
