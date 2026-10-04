import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth";

export default async function OperationsLayout({ children }: { children: ReactNode }) {
  await requireRole("event_operations_manager");
  return children;
}
