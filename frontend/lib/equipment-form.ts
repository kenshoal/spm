import { isOperationalStatus, type OperationalStatus } from "./equipment-options";

export function parseQuantity(value: string): number | null {
  const text = value.trim();
  return /^\d+$/.test(text) ? Number(text) : null;
}

function text(formData: FormData, field: string): string {
  return String(formData.get(field) ?? "").trim();
}

export function parseEquipmentForm(formData: FormData) {
  const status = text(formData, "operational_status");
  const payload = {
    type: text(formData, "type"),
    description: text(formData, "description") || null,
    total_owned_quantity: parseQuantity(text(formData, "total_owned_quantity")),
    home_location: text(formData, "home_location"),
    operational_status: (isOperationalStatus(status) ? status : "AVAILABLE") as OperationalStatus,
  };
  const errors: Record<string, string> = {};
  if (!payload.type) errors.type = "Enter the equipment type.";
  if (!payload.home_location) errors.home_location = "Enter the home location.";
  if (payload.total_owned_quantity === null) errors.total_owned_quantity = "Enter a whole number of zero or more.";
  return { payload, errors };
}

// Reads the form's raw, trimmed text — the counterpart to parseEquipmentForm's
// typed, validated payload. Used to echo a failed submission's exact typed
// values back into the form: React resets a <form>'s uncontrolled fields to
// their rendered defaultValue as soon as its action is submitted, even when
// the action only returns validation errors, so without this a corrected
// resubmission would fire with the *other* fields blanked back out.
export function readEquipmentFormValues(formData: FormData): Record<string, string> {
  return {
    type: text(formData, "type"),
    description: text(formData, "description"),
    total_owned_quantity: text(formData, "total_owned_quantity"),
    home_location: text(formData, "home_location"),
    operational_status: text(formData, "operational_status"),
  };
}
