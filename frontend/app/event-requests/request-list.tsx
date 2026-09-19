import Link from "next/link";
import type { EventRequest } from "@/lib/event-requests";
import { formatDateTime } from "@/lib/event-requests";
import { ArrowIcon, CalendarIcon, PeopleIcon } from "../components/icons";
import { DeleteDraftButton } from "./delete-draft-button";

export function RequestList({
  requests,
  emptyMessage = "Your saved drafts will appear here.",
}: {
  requests: EventRequest[];
  emptyMessage?: string;
}) {
  if (requests.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center">
        <p className="font-semibold text-[#273832]">No event requests yet</p>
        <p className="mt-2 text-sm text-[#718078]">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {requests.map((request) => (
        <article
          key={request.id}
          className="grid gap-4 rounded-2xl border border-[#dce4e0] bg-white p-5 shadow-[0_1px_2px_rgba(22,46,37,0.04)] transition hover:border-[#a9c8be] hover:shadow-[0_8px_24px_rgba(22,46,37,0.08)] sm:grid-cols-[1fr_auto] sm:items-center sm:p-6"
        >
          <Link
            href={`/event-requests/${request.id}/edit`}
            className="group min-w-0 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#0f6b5b]"
          >
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="truncate text-base font-bold text-[#1b2b25] sm:text-lg">{request.event_name ?? "Untitled event request"}</h2>
              <span className="rounded-full bg-[#eef4f1] px-2.5 py-1 text-xs font-bold text-[#315047]">Draft</span>
            </div>
            <p className="mt-2 line-clamp-1 text-sm text-[#68776f]">{request.purpose ?? "Purpose not provided yet"}</p>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-[#718078]">
              <span className="inline-flex items-center gap-1.5"><CalendarIcon className="size-4" />{request.proposed_date_times[0] ? formatDateTime(request.proposed_date_times[0]) : "Date not set"}</span>
              <span className="inline-flex items-center gap-1.5"><PeopleIcon className="size-4" />{request.expected_attendance ? `${request.expected_attendance} attendees` : "Attendance not set"}</span>
              <span>Updated {formatDateTime(request.updated_at)}</span>
            </div>
          </Link>
          <div className="flex items-center justify-between gap-2 border-t border-[#edf1ef] pt-3 sm:flex-col-reverse sm:items-end sm:border-0 sm:pt-0">
            {request.status === "Draft" ? (
              <DeleteDraftButton
                eventRequestId={request.id}
                eventName={request.event_name}
              />
            ) : null}
            <Link
              href={`/event-requests/${request.id}/edit`}
              className="group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-semibold text-[#0f6b5b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b]"
            >
              Continue draft
              <ArrowIcon className="size-5 transition-transform group-hover:translate-x-1" />
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}
