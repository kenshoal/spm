import type { EventRequestStatus } from "@/lib/event-requests";

/**
 * SCRUM-40 AC9: a Confirmed or Planning event with no recorded final end is never completed
 * automatically, so the assigned Coordinator is told instead of the event being skipped silently.
 */
export function FinalEndWarning({ status, finalEventEndAt }: {
  status: EventRequestStatus;
  finalEventEndAt?: string | null;
}) {
  if (finalEventEndAt || (status !== "Confirmed" && status !== "Planning")) return null;
  return (
    <div role="status" className="mt-5 rounded-xl border border-[#e8d9a8] bg-[#fffaf0] px-4 py-3 text-sm text-[#6b4f10]">
      <p className="font-semibold">No final event end recorded.</p>
      <p className="mt-1">
        This event will not complete automatically until an end is recorded.{" "}
        {status === "Planning"
          ? "Record the final event end below before the event is confirmed."
          : "An end cannot be added after confirmation, so mark the event completed yourself once it has finished."}
      </p>
    </div>
  );
}
