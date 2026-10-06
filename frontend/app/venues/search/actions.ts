"use server";

import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireAnyRole } from "@/lib/auth";
import { buildSuitabilityRequest, type SuitabilityFormValues, type SuitabilityResult } from "@/lib/venue-suitability";
import { venueApiUrl } from "@/lib/venues";

export interface SuitabilityState {
  result?: SuitabilityResult;
  message?: string;
  errors?: Record<string, string>;
  // The last submitted raw text, so the form keeps what was typed (React
  // resets uncontrolled fields to their defaultValue when an action runs).
  values?: SuitabilityFormValues;
}

const FIELDS = ["expected_attendance", "required_layout", "required_slot", "required_facilities", "required_accessibility"] as const;

function readValues(formData: FormData): SuitabilityFormValues {
  return Object.fromEntries(FIELDS.map((field) => [field, String(formData.get(field) ?? "")])) as unknown as SuitabilityFormValues;
}

// Advisory only: this makes one POST to the suitability endpoint and nothing
// else, so a check never books, holds or changes the venue.
export async function checkVenueSuitability(
  venueId: string,
  previousState: SuitabilityState,
  formData: FormData,
): Promise<SuitabilityState> {
  const values = readValues(formData);
  const { payload, errors } = buildSuitabilityRequest(values);
  if (!payload) return { errors, values };

  await requireAnyRole(["event_coordinator", "venue_staff"]);
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, `/venues/${encodeURIComponent(venueId)}/suitability`, "POST", payload);
  } catch {
    return { message: "The suitability check could not be completed. Please try again.", values };
  }
  if (response.status === 401) redirect("/auth");
  if (response.status === 404) return { message: "This venue no longer exists.", values };
  if (!response.ok) return { message: "The suitability check could not be completed. Please try again.", values };
  return { result: (await response.json()) as SuitabilityResult, values };
}
