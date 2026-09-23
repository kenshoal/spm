import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth";

export default async function CoordinationLayout({ children }: { children: ReactNode }) {
  await requireRole("event_coordinator");
  return children;
}
