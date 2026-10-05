"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { notificationApi } from "@/lib/notifications";

export interface MarkReadState {
  message?: string;
}

export async function markNotificationRead(
  notificationId: string,
  previousState: MarkReadState,
): Promise<MarkReadState> {
  void previousState;
  let response: Response;
  try {
    response = await sendJson(
      notificationApi,
      `/notifications/${encodeURIComponent(notificationId)}/read`,
      "PATCH",
      {},
    );
  } catch {
    return { message: "Couldn't mark this as read. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 404
          ? "This notification no longer exists. Refresh the page."
          : "Couldn't mark this as read. Please try again.",
    };
  }
  revalidatePath("/notifications");
  return {};
}
