"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { equipmentApiUrl, isOperationalStatus, statusLabel, type OperationalStatus } from "@/lib/equipment";
import { parseEquipmentForm, parseQuantity, readEquipmentFormValues } from "@/lib/equipment-form";

export interface EquipmentFormState {
  message?: string;
  errors?: Record<string, string>;
  saved?: boolean;
  // Echoes the last submitted *raw* field text so the form can repopulate
  // itself. React resets a <form>'s uncontrolled fields whenever its action
  // promise settles, even when the action just returns validation errors
  // instead of throwing — so without this, a corrected resubmission would
  // fire with the *other* fields blanked back out.
  values?: Record<string, string>;
}

function failure(status: number, fallback: string): EquipmentFormState {
  return {
    message:
      status === 403
        ? "Only Technical Support Staff can change equipment."
        : status === 404
          ? "This equipment record no longer exists."
          : fallback,
  };
}

export async function createEquipment(previousState: EquipmentFormState, formData: FormData): Promise<EquipmentFormState> {
  void previousState;
  const { payload, errors } = parseEquipmentForm(formData);
  const values = readEquipmentFormValues(formData);
  if (Object.keys(errors).length) return { message: "Check the highlighted fields.", errors, values };

  await requireRole("technical_support");
  let response: Response;
  try {
    response = await sendJson(equipmentApiUrl, "/equipment", "POST", payload);
  } catch {
    return { message: "The equipment could not be saved. Please try again.", values };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return { ...failure(response.status, "The equipment could not be saved. Please try again."), values };
  const created = (await response.json()) as { id: string };
  revalidatePath("/equipment");
  redirect(`/equipment/${created.id}`);
}

export async function updateEquipmentQuantity(
  equipmentId: string,
  previousState: EquipmentFormState,
  formData: FormData,
): Promise<EquipmentFormState> {
  void previousState;
  const raw = String(formData.get("total_owned_quantity") ?? "").trim();
  const quantity = parseQuantity(raw);
  if (quantity === null) return { message: "Enter a whole number of zero or more.", values: { total_owned_quantity: raw } };

  await requireRole("technical_support");
  let response: Response;
  try {
    response = await sendJson(equipmentApiUrl, `/equipment/${encodeURIComponent(equipmentId)}/quantity`, "PATCH", { total_owned_quantity: quantity });
  } catch {
    return { message: "The quantity could not be updated. Please try again.", values: { total_owned_quantity: raw } };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return { ...failure(response.status, "The quantity could not be updated. Please try again."), values: { total_owned_quantity: raw } };
  }
  revalidatePath("/equipment");
  revalidatePath(`/equipment/${equipmentId}`);
  return { saved: true, message: "Quantity updated." };
}

export async function changeEquipmentStatus(
  equipmentId: string,
  currentStatus: OperationalStatus,
  previousState: EquipmentFormState,
  formData: FormData,
): Promise<EquipmentFormState> {
  void previousState;
  const newStatus = String(formData.get("new_status") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  const values = { new_status: newStatus, reason };
  if (!isOperationalStatus(newStatus) || newStatus === currentStatus) return { message: "Choose a different status.", values };
  if (reason.length > 255) return { message: "Keep the reason to 255 characters or fewer.", values };

  await requireRole("technical_support");
  let response: Response;
  try {
    response = await sendJson(equipmentApiUrl, `/equipment/${encodeURIComponent(equipmentId)}/status`, "PATCH", { new_status: newStatus, reason: reason || null });
  } catch {
    return { message: "The status could not be changed. Please try again.", values };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return { ...failure(response.status, "The status could not be changed. Please try again."), values };
  revalidatePath("/equipment");
  revalidatePath(`/equipment/${equipmentId}`);
  return { saved: true, message: `Status changed to ${statusLabel(newStatus)}.` };
}
