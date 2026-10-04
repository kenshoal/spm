import type { ReactNode } from "react";
import { requireEventOrganiser } from "@/lib/auth";

export default async function EventRequestsLayout({ children }: { children: ReactNode }) {
  await requireEventOrganiser();
  return children;
}
