import { unstable_rethrow } from "next/navigation";
import { getJson } from "@/lib/api";
import { formatDateTime } from "@/lib/event-requests";
import { OfferPlaceButton } from "./offer-place-button";

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

interface WaitlistRow {
  id: string;
  attendee_id: string;
  attendee_email: string | null;
  status: "Waiting" | "Offered";
  queued_at: string;
  expires_at: string | null;
}

// SCRUM-24 AC3 (Q&A #26): the queue is FIFO, and the Coordinator may override it.
export async function WaitlistPanel({ eventRequestId }: { eventRequestId: string }) {
  let rows: WaitlistRow[] | null = null;
  try {
    rows = await getJson<WaitlistRow[]>(apiUrl, `/event-requests/${encodeURIComponent(eventRequestId)}/waitlist`);
  } catch (error) {
    unstable_rethrow(error);
  }
  return (
    <section aria-label="Waiting list" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Waiting list</h2>
      {rows === null ? (
        <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">The waiting list could not be loaded. Refresh to try again.</p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-sm text-[#718078]">No one is waiting.</p>
      ) : (
        <ol className="mt-3 space-y-2 text-sm">
          {rows.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[#f4f7f5] px-4 py-3">
              <span className="break-all">
                <span className="font-semibold text-[#17211d]">{row.attendee_email ?? row.attendee_id}</span>
                {" · "}{row.status === "Offered" && row.expires_at ? `Offered until ${formatDateTime(row.expires_at)}` : "Waiting"}
              </span>
              {row.status === "Waiting" ? <OfferPlaceButton eventRequestId={eventRequestId} entryId={row.id} /> : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
