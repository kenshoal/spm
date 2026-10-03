import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { VenueForm } from "../venue-form";

export default async function NewVenuePage() {
  const user = await requireRole("venue_staff");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-3xl">
        <Link href="/venues" className="mb-5 inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to venues</Link>
        <h1 className="mb-6 text-3xl font-bold tracking-[-0.035em] text-[#17211d]">Add a venue</h1>
        <VenueForm />
      </div>
    </AppShell>
  );
}
