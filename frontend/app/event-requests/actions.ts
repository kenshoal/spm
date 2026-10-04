"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireAccessToken, requireRole } from "@/lib/auth";

export interface EventRequestFormState {
  message?: string;
  errors?: Record<string, string>;
}

export interface DeleteEventRequestState {
  deleted?: boolean;
  message?: string;
}

export interface ClarificationResponseState {
  submitted?: boolean;
  message?: string;
  errors?: { response?: string };
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

function optionalText(formData: FormData, field: string): string | null {
  const value = String(formData.get(field) ?? "").trim();
  return value || null;
}

function singaporeDateTimeToIso(value: FormDataEntryValue): string | null {
  const localValue = String(value).trim();
  if (!localValue) return null;

  const date = new Date(`${localValue}:00+08:00`);
  return Number.isNaN(date.getTime()) ? localValue : date.toISOString();
}

function parseEventRequestForm(formData: FormData) {
  const attendanceText = String(formData.get("expected_attendance") ?? "").trim();
  const attendance = attendanceText ? Number(attendanceText) : null;
  const proposedDateTimes = formData
    .getAll("proposed_date_times")
    .map(singaporeDateTimeToIso)
    .filter((value): value is string => value !== null);

  const payload = {
    event_name: optionalText(formData, "event_name"),
    purpose: optionalText(formData, "purpose"),
    description: optionalText(formData, "description"),
    proposed_date_times: proposedDateTimes,
    expected_attendance: attendance,
    venue_requirements: optionalText(formData, "venue_requirements"),
    accessibility_needs: optionalText(formData, "accessibility_needs"),
    equipment_requirements: optionalText(formData, "equipment_requirements"),
    registration_needs: optionalText(formData, "registration_needs"),
  };

  const errors: Record<string, string> = {};
  if (attendance !== null && (!Number.isInteger(attendance) || attendance <= 0)) {
    errors.expected_attendance = "Enter a whole number greater than zero.";
  }
  return { payload, errors };
}

function validateSubmission(
  payload: ReturnType<typeof parseEventRequestForm>["payload"],
): Record<string, string> {
  const errors: Record<string, string> = {};
  const requiredTextFields = [
    "event_name",
    "purpose",
    "description",
    "venue_requirements",
    "accessibility_needs",
    "equipment_requirements",
    "registration_needs",
  ] as const;
  for (const field of requiredTextFields) {
    if (!payload[field]) errors[field] = "Complete this field before submitting.";
  }
  if (!payload.proposed_date_times.length) {
    errors.proposed_date_times = "Add at least one proposed date and time.";
  }
  if (payload.expected_attendance === null) {
    errors.expected_attendance = "Enter the expected attendance.";
  }
  return errors;
}

async function submitEventRequest(
  path: string,
  formData: FormData,
): Promise<EventRequestFormState> {
  const { payload, errors: parsingErrors } = parseEventRequestForm(formData);
  const errors = { ...parsingErrors, ...validateSubmission(payload) };
  if (Object.keys(errors).length) {
    return { message: "Complete all required fields before submitting.", errors };
  }

  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
  } catch {
    return { message: "The request could not be submitted. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 409
          ? "This request has already been submitted and is now read-only."
          : response.status === 422
            ? "Complete all required fields before submitting."
            : "The request could not be submitted. Please try again.",
    };
  }

  revalidatePath("/event-requests");
  redirect("/event-requests?status=submitted");
}

export async function createEventRequest(
  _previousState: EventRequestFormState,
  formData: FormData,
): Promise<EventRequestFormState> {
  const { payload, errors } = parseEventRequestForm(formData);
  if (Object.keys(errors).length) {
    return { message: "Check the highlighted fields.", errors };
  }

  await requireRole("event_organiser");
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}/event-requests`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return { message: "The request could not be saved. Please try again." };
  }

  revalidatePath("/event-requests");
  redirect("/event-requests");
}

export async function updateEventRequest(
  eventRequestId: string,
  _previousState: EventRequestFormState,
  formData: FormData,
): Promise<EventRequestFormState> {
  const { payload, errors } = parseEventRequestForm(formData);
  if (Object.keys(errors).length) {
    return { message: "Check the highlighted fields.", errors };
  }

  await requireRole("event_organiser");
  const token = await requireAccessToken();
  const response = await fetch(
    `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    },
  );
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 409
          ? "This request is no longer an editable draft."
          : "The changes could not be saved. Please try again.",
    };
  }

  revalidatePath("/event-requests");
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  redirect("/event-requests");
}

export async function submitNewEventRequest(
  _previousState: EventRequestFormState,
  formData: FormData,
): Promise<EventRequestFormState> {
  return submitEventRequest("/event-requests/submissions", formData);
}

export async function submitDraftEventRequest(
  eventRequestId: string,
  _previousState: EventRequestFormState,
  formData: FormData,
): Promise<EventRequestFormState> {
  return submitEventRequest(
    `/event-requests/${encodeURIComponent(eventRequestId)}/submit`,
    formData,
  );
}

export async function respondToClarification(
  eventRequestId: string,
  _previousState: ClarificationResponseState,
  formData: FormData,
): Promise<ClarificationResponseState> {
  await requireRole("event_organiser");
  const responseText = String(formData.get("response") ?? "").trim();
  if (!responseText) {
    return {
      message: "Enter a response before sending it.",
      errors: { response: "Explain the clarification for your coordinator." },
    };
  }

  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/clarification-response`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ response: responseText }),
      },
    );
  } catch {
    return { message: "The clarification could not be sent. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 409
          ? "This clarification has already been answered or review has continued."
          : "The clarification could not be sent. Please try again.",
    };
  }

  revalidatePath("/event-requests");
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  return { submitted: true };
}

export async function deleteEventRequest(
  eventRequestId: string,
  previousState: DeleteEventRequestState,
  formData: FormData,
): Promise<DeleteEventRequestState> {
  void previousState;
  void formData;

  await requireRole("event_organiser");
  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}`,
      {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      },
    );
  } catch {
    return { message: "The draft could not be deleted. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 404
          ? "This draft could not be found. Refresh the page and try again."
          : response.status === 409
            ? "Only draft requests can be deleted."
            : "The draft could not be deleted. Please try again.",
    };
  }
  revalidatePath("/event-requests");
  return { deleted: true };
}
