"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { parseVenueForm, readVenueFormValues, type VenueFormValues } from "@/lib/venue-form";
import { venueApiUrl } from "@/lib/venues";

export interface VenueFormState {
  message?: string;
  errors?: Record<string, string>;
  // Echoes the last submitted *raw* field text so the form can repopulate
  // itself. React resets a <form>'s uncontrolled fields to their rendered
  // defaultValue the moment the action is submitted (before it even
  // resolves), even when the action just returns validation errors instead
  // of throwing — so without this, a corrected resubmission would fire with
  // the *other* fields blanked back out. This must be the raw
  // text, not the parsed payload: an invalid capacity parses to `null`,
  // which would let a field-by-field fallback silently revert to the
  // venue's stored value instead of showing what was actually typed.
  values?: VenueFormValues;
}

async function saveVenue(
  path: string,
  method: "POST" | "PATCH",
  formData: FormData,
): Promise<VenueFormState> {
  const { payload, errors } = parseVenueForm(formData, { includeStatus: method === "PATCH" });
  if (Object.keys(errors).length) {
    return { message: "Check the highlighted fields.", errors, values: readVenueFormValues(formData) };
  }

  await requireRole("venue_staff");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, path, method, payload);
  } catch {
    return { message: "The venue could not be saved. Please try again.", values: readVenueFormValues(formData) };
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
              ? "The venue service rejected these details. Check them and try again."
              : "The venue could not be saved. Please try again.",
      values: readVenueFormValues(formData),
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
