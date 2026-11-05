"use client";

import { useState } from "react";
import type { EventRegistration } from "@/lib/registration-info";
import { formatSingaporeDateTime as formatDateTime } from "@/lib/singapore-time";
import { CheckInButton } from "../coordination/requests/[id]/check-in-button";

// Hotfix 16 (SCRUM-25 manual lookup, Q&A #32): find a person by email at the counter.
export function RegistrationTable({ eventRequestId, registrations, canCheckIn }: {
  eventRequestId: string;
  registrations: EventRegistration[];
  canCheckIn: boolean;
}) {
  const [search, setSearch] = useState("");
  const wanted = search.trim().toLowerCase();
  const shown = registrations.filter((row) =>
    !wanted || (row.attendee_email ?? row.attendee_id).toLowerCase().includes(wanted),
  );
  return (
    <>
      <label className="mt-4 block text-sm font-semibold text-[#34463f]">Find an attendee
        <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Email" className="mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]" />
      </label>
      {shown.length === 0 ? <p className="mt-3 text-sm text-[#68776f]">No attendee matches that search.</p> : (
        <div className="overflow-x-auto">
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-xs text-[#68776f]"><tr><th className="py-2">Attendee</th><th>Status</th><th>Registered</th><th>Added by</th><th>Checked in</th></tr></thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.id} className="border-t border-[#e1e7e4]">
                  <td className="py-2 break-all">{row.attendee_email ?? <span className="font-mono text-xs">{row.attendee_id}</span>}</td>
                  <td>{row.status}</td>
                  <td><time dateTime={row.created_at}>{formatDateTime(row.created_at)}</time></td>
                  <td>{row.registered_by ? `Coordinator ${row.registered_by}` : "Self"}</td>
                  <td>
                    {row.attended_at ? (
                      <time dateTime={row.attended_at}>{formatDateTime(row.attended_at)}</time>
                    ) : canCheckIn && row.status === "Registered" ? (
                      <CheckInButton eventRequestId={eventRequestId} registrationId={row.id} />
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
