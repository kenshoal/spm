import { unstable_rethrow } from "next/navigation";
import { formatDateTime } from "@/lib/event-requests";
import { getRegistrationInfo, type RegistrationInfo } from "@/lib/registration-info";
import { CheckInButton } from "../coordination/requests/[id]/check-in-button";
import { ManualRegistrationForm } from "../coordination/requests/[id]/manual-registration-form";

const sectionClass = "mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6";

/** SCRUM-34: attendees are shown by account id only; no contact details exist here. */
export async function RegistrationInfoPanel({ eventRequestId, canAddAttendee = false, canCheckIn = false }: {
  eventRequestId: string; canAddAttendee?: boolean; canCheckIn?: boolean;
}) {
  let info: RegistrationInfo;
  try {
    info = await getRegistrationInfo(eventRequestId);
  } catch (error) {
    unstable_rethrow(error);
    return <section aria-label="Registrations" className={sectionClass}><h2 className="text-lg font-bold">Registrations</h2><p role="alert" className="mt-3 text-sm text-[#793f27]">Registration information is temporarily unavailable. Refresh to try again.</p></section>;
  }
  const counts = [
    ["Registered", info.registered],
    ["Withdrawn", info.withdrawn],
    ["Places available", info.places_available ?? "Not set"],
    ["Checked in", info.attended],
    ["Not checked in", info.absent],
  ] as const;
  return (
    <section aria-label="Registrations" className={sectionClass}>
      <h2 className="text-lg font-bold text-[#17211d]">Registrations</h2>
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {counts.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-[#f4f7f5] px-4 py-3">
            <dt className="text-xs text-[#68776f]">{label}</dt>
            <dd className="text-xl font-bold text-[#17211d]">{value}</dd>
          </div>
        ))}
      </dl>
      {info.registrations.length === 0 ? (
        <p className="mt-4 text-sm text-[#68776f]">No one has registered yet.</p>
      ) : (
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-xs text-[#68776f]"><tr><th className="py-2">Attendee</th><th>Status</th><th>Registered</th><th>Added by</th><th>Checked in</th></tr></thead>
          <tbody>
            {info.registrations.map((row) => (
              <tr key={row.id} className="border-t border-[#e1e7e4]">
                <td className="py-2 font-mono text-xs break-all">{row.attendee_id}</td>
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
      )}
      {canAddAttendee ? <ManualRegistrationForm eventRequestId={eventRequestId} /> : null}
    </section>
  );
}

export function RegistrationInfoLoading() {
  return <p role="status" className="mt-5 p-6 text-sm text-[#68776f]">Loading registrations…</p>;
}
