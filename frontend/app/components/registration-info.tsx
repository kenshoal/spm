import { unstable_rethrow } from "next/navigation";
import { getRegistrationInfo, type RegistrationInfo } from "@/lib/registration-info";
import { RegistrationSettingsForm } from "../coordination/requests/[id]/registration-settings-form";
import { RegistrationTable } from "./registration-table";
import { ManualRegistrationForm } from "../coordination/requests/[id]/manual-registration-form";

const sectionClass = "mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6";

/** SCRUM-34: each registration with its attendee (hotfix 16 adds their email, Q&A #32). */
export async function RegistrationInfoPanel({ eventRequestId, canAddAttendee = false, canCheckIn = false, canSetSettings = false }: {
  eventRequestId: string; canAddAttendee?: boolean; canCheckIn?: boolean; canSetSettings?: boolean;
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
        <RegistrationTable eventRequestId={eventRequestId} registrations={info.registrations} canCheckIn={canCheckIn} />
      )}
      {canSetSettings ? (
        <RegistrationSettingsForm
          eventRequestId={eventRequestId}
          opensAt={info.registration_opens_at ?? null}
          closesAt={info.registration_closes_at ?? null}
          capacity={info.registration_capacity}
        />
      ) : null}
      {canAddAttendee ? <ManualRegistrationForm eventRequestId={eventRequestId} /> : null}
    </section>
  );
}

export function RegistrationInfoLoading() {
  return <p role="status" className="mt-5 p-6 text-sm text-[#68776f]">Loading registrations…</p>;
}
