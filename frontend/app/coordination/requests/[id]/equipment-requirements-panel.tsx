import { unstable_rethrow } from "next/navigation";
import { listEquipment } from "@/lib/equipment";
import {
  listEventRequirements,
  REQUIREMENT_STATUS_LABELS,
  type EquipmentRequirement,
} from "@/lib/equipment-requests";
import { EquipmentRequirementForm } from "./equipment-requirement-form";

// Hotfix 7 (SCRUM-33): the event's equipment needs and how far each has got.
export async function EquipmentRequirementsPanel({ eventRequestId, canRecord }: { eventRequestId: string; canRecord: boolean }) {
  let requirements: EquipmentRequirement[] | null = null;
  try {
    requirements = await listEventRequirements(eventRequestId);
  } catch (error) {
    unstable_rethrow(error);
  }
  const types = await listEquipment().then((rows) => [...new Set(rows.map((row) => row.type))]).catch((error: unknown) => {
    unstable_rethrow(error);
    return [] as string[];
  });
  return (
    <section aria-label="Equipment requirements" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Equipment requirements</h2>
      {requirements === null ? (
        <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Equipment requirements could not be loaded. Refresh to try again.</p>
      ) : requirements.length === 0 ? (
        <p className="mt-3 text-sm text-[#718078]">No equipment recorded yet.</p>
      ) : (
        <ul className="mt-3 space-y-2 text-sm">
          {requirements.map((requirement) => (
            <li key={requirement.id} className="rounded-xl bg-[#f4f7f5] px-4 py-3">
              <span className="font-semibold text-[#17211d]">{requirement.quantity} × {requirement.equipment_type}</span>
              {" · "}{REQUIREMENT_STATUS_LABELS[requirement.status]}
              {requirement.technical_requirements ? <p className="mt-1 text-[#526159]">{requirement.technical_requirements}</p> : null}
              {requirement.support_note ? <p className="mt-1 text-[#526159]">Technical Support: {requirement.support_note}</p> : null}
            </li>
          ))}
        </ul>
      )}
      {canRecord ? <EquipmentRequirementForm eventRequestId={eventRequestId} types={types} /> : null}
    </section>
  );
}
