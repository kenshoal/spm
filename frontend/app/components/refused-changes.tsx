import type { EventChangeRequest } from "@/lib/event-requests";
import { CHANGE_FIELD_LABELS } from "@/lib/change-decision";
import { formatDateTime } from "@/lib/event-requests";

function valueText(key: string, value: unknown): string {
  if (key === "proposed_date_times" && Array.isArray(value)) {
    return value.map((item) => formatDateTime(String(item))).join(", ");
  }
  return Array.isArray(value) ? value.map(String).join(", ") : String(value);
}

/** Hotfix 20 (Q&A #104): what a partly approved change did not apply, and why. */
export function RefusedChanges({ request }: { request: Pick<EventChangeRequest, "status" | "rejected_changes"> }) {
  const refused = Object.entries(request.rejected_changes ?? {});
  if (request.status !== "Partially Approved" || refused.length === 0) return null;
  return (
    <div className="mt-3 rounded-lg bg-[#fff8ec] px-3 py-3 text-sm">
      <p className="font-semibold text-[#7a4b0c]">Not accepted</p>
      <ul className="mt-2 space-y-2">
        {refused.map(([key, detail]) => (
          <li key={key}>
            <strong>{CHANGE_FIELD_LABELS[key] ?? key}:</strong> {valueText(key, detail.value)}
            <br />
            <span className="text-[#526159]">Reason: {detail.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
