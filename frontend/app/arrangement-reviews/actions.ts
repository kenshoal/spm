"use server";

import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { arrangementRoles, clearArrangementReview, type Arrangement } from "@/lib/arrangement-reviews";

export interface ReviewClearState { message?: string }

export async function markArrangementReviewed(
  reviewId: string, arrangement: Arrangement, previous: ReviewClearState, formData: FormData,
): Promise<ReviewClearState> {
  void previous;
  const role = arrangementRoles[arrangement];
  if (!role) return { message: "This review cannot be marked from this workspace." };
  await requireRole(role);
  if (formData.get("reviewed") !== "on") {
    return { message: "Confirm that you have checked the referenced arrangement first." };
  }
  let response: Response;
  try {
    response = await clearArrangementReview(reviewId);
  } catch (error) {
    unstable_rethrow(error);
    return { message: "The review could not be saved. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (response.status === 403) return { message: "You no longer have permission to mark this review." };
  if (response.status === 404) return { message: "This review is no longer available. Refresh the queue." };
  if (response.status === 409) return { message: "This review has already been marked. Refresh the queue." };
  if (!response.ok) return { message: "The review could not be saved. Please try again." };
  revalidatePath("/arrangement-reviews");
  revalidatePath("/coordination/requests/[id]", "page");
  redirect(`/arrangement-reviews?arrangement=${arrangement}&reviewed=1`);
}
