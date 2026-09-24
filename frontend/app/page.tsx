import { redirect } from "next/navigation";
import { requireAuthenticatedUser, workspaceForRoles } from "@/lib/auth";

export default async function HomePage() {
  const user = await requireAuthenticatedUser();
  redirect(workspaceForRoles(user.roles));
}
