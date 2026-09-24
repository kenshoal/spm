import { getJson } from "./api";
import type { OperationalStatus } from "./equipment-options";

export { OPERATIONAL_STATUSES, statusLabel, isOperationalStatus } from "./equipment-options";
export type { OperationalStatus } from "./equipment-options";

export interface Equipment {
  id: string;
  type: string;
  description: string | null;
  total_owned_quantity: number;
  home_location: string;
  operational_status: OperationalStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export const equipmentApiUrl = process.env.EQUIPMENT_API_URL ?? "http://127.0.0.1:8002";

export async function listEquipment(status?: OperationalStatus): Promise<Equipment[]> {
  const query = status ? `?operational_status=${status}` : "";
  return (await getJson<Equipment[]>(equipmentApiUrl, `/equipment${query}`)) ?? [];
}

export async function getEquipment(id: string): Promise<Equipment | null> {
  return getJson<Equipment>(equipmentApiUrl, `/equipment/${encodeURIComponent(id)}`);
}
