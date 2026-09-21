import type { EventRequest } from "@/lib/event-requests";
import { formatDateTime } from "@/lib/event-requests";

const requirementFields = [
  ["venue_requirements", "Venue requirements"],
  ["equipment_requirements", "Equipment requirements"],
  ["accessibility_needs", "Accessibility needs"],
  ["registration_needs", "Registration needs"],
] as const;

export function RequestDetails({ request }: { request: EventRequest }) {
  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold text-[#17211d]">{request.event_name}</h1>
          <span className="rounded-full bg-[#fff3dc] px-3 py-1 text-xs font-bold text-[#80520d]">{request.status}</span>
        </div>
        <dl className="mt-6 grid gap-5 sm:grid-cols-2">
          <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Purpose</dt><dd className="mt-1 text-sm leading-6 text-[#273832]">{request.purpose}</dd></div>
          <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Expected attendance</dt><dd className="mt-1 text-sm leading-6 text-[#273832]">{request.expected_attendance}</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Description</dt><dd className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[#273832]">{request.description}</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Proposed dates</dt><dd className="mt-1 text-sm leading-6 text-[#273832]">{request.proposed_date_times.map(formatDateTime).join(", ")}</dd></div>
        </dl>
      </section>
      <section className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
        <h2 className="text-lg font-bold text-[#17211d]">Event requirements</h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2">
          {requirementFields.map(([field, label]) => (
            <div key={field}>
              <dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">{label}</dt>
              <dd className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[#273832]">{request[field]}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
