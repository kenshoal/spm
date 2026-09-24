import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth";

export default async function EquipmentLayout({ children }: { children: ReactNode }) {
  await requireRole("technical_support");
  return children;
}
