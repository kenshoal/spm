import { unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { listEquipment, type Equipment } from "@/lib/equipment";
import {
  listEquipmentRequirements,
  listEventReservations,
  listVenueLocations,
  REQUIREMENT_STATUS_LABELS,
  singaporeDate,
  type EquipmentRequirement,
  type EquipmentReservation,
  type VenueLocation,
} from "@/lib/equipment-requests";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { ArrangementForm, AvailabilityForm, ReleaseForm, ReserveForm } from "./request-forms";

async function reservationsOf(requirement: EquipmentRequirement): Promise<EquipmentReservation[] | null> {
  try {
    return (await listEventReservations(requirement.event_request_id)).filter((row) => row.requirement_id === requirement.id);
  } catch (error) {
    unstable_rethrow(error);
    return null;
  }
}

// Hotfix 7 (SCRUM-10, SCRUM-13, SCRUM-33): Technical Support reviews what events
// need, checks availability, reserves, releases and moves each arrangement along.
export default async function EquipmentRequestsPage() {
  const user = await requireRole("technical_support");
  let requirements: EquipmentRequirement[] | null = null;
  let equipment: Equipment[] = [];
  let venues: VenueLocation[] = [];
  try {
    [requirements, equipment, venues] = await Promise.all([listEquipmentRequirements(), listEquipment(), listVenueLocations()]);
  } catch (error) {
    unstable_rethrow(error);
  }
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Technical support workspace</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Equipment requests</h1>
      </div>
      {requirements === null ? (
        <p role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">Equipment requests could not be loaded. Refresh to try again.</p>
      ) : requirements.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No event has asked for equipment yet.</p>
      ) : (
        <ul className="space-y-6">
          {await Promise.all(requirements.map(async (requirement) => {
            const reservations = await reservationsOf(requirement);
            const reserved = (reservations ?? []).reduce((total, row) => total + row.quantity, 0);
            const defaults = {
              venues: venues.map(({ id, name }) => ({ id, name })),
              startDate: singaporeDate(requirement.event_date_times[0]),
              endDate: singaporeDate(requirement.event_date_times.at(-1)),
              quantity: Math.max(requirement.quantity - reserved, 1),
            };
            const matching = equipment
              .filter((item) => item.type.trim().toLowerCase() === requirement.equipment_type.trim().toLowerCase() && item.operational_status === "AVAILABLE")
              .map((item) => ({ id: item.id, label: `${item.type} · ${item.home_location} · ${item.total_owned_quantity} owned` }));
            return (
              <li key={requirement.id} className="rounded-2xl border border-[#dce4e0] bg-white p-6">
                <h2 className="text-lg font-bold text-[#17211d]">{requirement.quantity} × {requirement.equipment_type} <span className="text-sm font-normal text-[#68776f]">for {requirement.event_name ?? "an event"}</span></h2>
                <p className="mt-1 text-sm text-[#526159]">{REQUIREMENT_STATUS_LABELS[requirement.status]} · {reserved} of {requirement.quantity} reserved</p>
                {requirement.technical_requirements ? <p className="mt-1 text-sm text-[#526159]">{requirement.technical_requirements}</p> : null}
                <div className="mt-4 space-y-4">
                  <AvailabilityForm requirementId={requirement.id} equipmentType={requirement.equipment_type} defaults={defaults} />
                  <ReserveForm requirementId={requirement.id} defaults={defaults} equipment={matching} />
                  {reservations === null ? (
                    <p role="alert" className="text-sm text-[#793f27]">Reservations could not be loaded.</p>
                  ) : reservations.map((row) => (
                    <div key={row.id} className="rounded-xl bg-[#f4f7f5] px-4 py-3 text-sm">
                      <p className="font-semibold text-[#17211d]">{row.quantity} reserved · {row.collection_date} to {row.return_date}</p>
                      <ReleaseForm reservationId={row.id} />
                    </div>
                  ))}
                  <ArrangementForm requirementId={requirement.id} status={requirement.status} note={requirement.support_note} />
                </div>
              </li>
            );
          }))}
        </ul>
      )}
    </AppShell>
  );
}
