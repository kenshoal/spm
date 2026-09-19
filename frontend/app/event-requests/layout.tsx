import type { ReactNode } from "react";
import { requireAuthenticatedUser } from "@/lib/auth";

export default async function EventRequestsLayout({ children }: { children: ReactNode }) {
  await requireAuthenticatedUser();
  return children;
}
