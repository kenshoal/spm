"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { parseBlockForm, readBlockFormValues, type BlockFormValues } from "@/lib/venue-block-form";
import { venueApiUrl } from "@/lib/venues";

export interface BlockFormState {
  message?: string;
  errors?: Record<string, string>;
  // The raw submitted text, so React's form reset doesn't lose what was typed.
  values?: BlockFormValues;
}

const failureMessages: Record<number, string> = {
  403: "Only Venue Staff can block venues.",
  404: "This venue no longer exists.",
  422: "The venue service rejected these details. Check them and try again.",
};
const retryMessage = "The block could not be saved. Please try again.";

export async function createVenueBlock(previousState: BlockFormState, formData: FormData): Promise<BlockFormState> {
  void previousState;
  const { venueId, payload, errors } = parseBlockForm(formData);
  if (Object.keys(errors).length) {
    return { message: "Check the highlighted fields.", errors, values: readBlockFormValues(formData) };
  }

  await requireRole("venue_staff");
  const venuePath = encodeURIComponent(venueId);
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, `/venues/${venuePath}/blocks`, "POST", payload);
  } catch {
    return { message: retryMessage, values: readBlockFormValues(formData) };
  }
  // redirect() throws, so it stays outside the try above.
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return { message: failureMessages[response.status] ?? retryMessage, values: readBlockFormValues(formData) };
  }
  revalidatePath("/venue-blocks");
  redirect(`/venue-blocks?venue=${venuePath}&month=${payload.start_date.slice(0, 7)}&created=1`);
}
