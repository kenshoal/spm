"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { parseVenueForm, type VenuePayload } from "@/lib/venue-form";
import { venueApiUrl } from "@/lib/venues";

export interface VenueFormState {
  message?: string;
  errors?: Record<string, string>;
  // Echoes the last submitted payload so the form can repopulate itself.
  // React resets a <form>'s uncontrolled fields whenever its action promise
  // settles, even when the action just returns validation errors instead of
  // throwing — so without this, a corrected resubmission would fire with the
  // *other* fields blanked back out. See __tests__ note in venue-form.tsx.
  values?: VenuePayload;
}

async function saveVenue(
  path: string,
  method: "POST" | "PATCH",
  formData: FormData,
): Promise<VenueFormState> {
  const { payload, errors } = parseVenueForm(formData, { includeStatus: method === "PATCH" });
  if (Object.keys(errors).length) return { message: "Check the highlighted fields.", errors, values: payload };

  await requireRole("venue_staff");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, path, method, payload);
  } catch {
    return { message: "The venue could not be saved. Please try again.", values: payload };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 403
          ? "Only Venue Staff can change the venue catalogue."
          : response.status === 404
            ? "This venue no longer exists."
            : response.status === 422
              ? "Check the highlighted fields."
              : "The venue could not be saved. Please try again.",
      values: payload,
    };
  }
  revalidatePath("/venues");
  redirect("/venues");
}

export async function createVenue(previousState: VenueFormState, formData: FormData): Promise<VenueFormState> {
  void previousState;
  return saveVenue("/venues", "POST", formData);
}

export async function updateVenue(
  venueId: string,
  previousState: VenueFormState,
  formData: FormData,
): Promise<VenueFormState> {
  void previousState;
  return saveVenue(`/venues/${encodeURIComponent(venueId)}`, "PATCH", formData);
}
