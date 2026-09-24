import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { getVenue } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../../../components/app-shell";
import { VenueForm } from "../../venue-form";

export default async function EditVenuePage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole("venue_staff");
  const { id } = await params;
  const result = await getVenue(id).then((venue) => ({ venue, failed: false as const })).catch((error: unknown) => {
    unstable_rethrow(error);
    return { venue: null, failed: true as const };
  });
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-3xl">
        <Link href="/venues" className="mb-5 inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to venues</Link>
        {result.failed ? (
          <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The venue service is unavailable. Start the local API on port 8004, then refresh.</div>
        ) : result.venue ? (
          <>
            <h1 className="mb-6 text-3xl font-bold tracking-[-0.035em] text-[#17211d]">Edit {result.venue.name}</h1>
            <VenueForm venue={result.venue} />
          </>
        ) : (
          <h1 className="text-xl font-bold">Venue not found</h1>
        )}
      </div>
    </AppShell>
  );
}
