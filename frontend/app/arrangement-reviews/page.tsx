import Link from "next/link";
import { redirect, unstable_rethrow } from "next/navigation";
import { requireAnyRole } from "@/lib/auth";
import { arrangementLabels, arrangementRoles, listDomainArrangementReviews, type Arrangement } from "@/lib/arrangement-reviews";
import { AppShell, workspaceLinks } from "../components/app-shell";
import { ArrangementReviewList } from "../components/arrangement-review-list";
import { RefreshArrangementReviews } from "../components/refresh-arrangement-reviews";

export default async function ArrangementReviewsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireAnyRole(["venue_staff", "technical_support"]);
  const params = await searchParams;
  const raw = Array.isArray(params.arrangement) ? params.arrangement[0] : params.arrangement;
  const domains = (Object.keys(arrangementRoles) as Arrangement[]).filter((domain) => user.roles.includes(arrangementRoles[domain]));
  const arrangement = raw === undefined ? domains[0] : raw;
  if (!domains.includes(arrangement as Arrangement)) redirect("/unauthorised");
  const selected = arrangement as Arrangement;
  const result = await listDomainArrangementReviews(selected)
    .then((reviews) => ({ reviews, failed: false }))
    .catch((error: unknown) => {
      unstable_rethrow(error);
      return { reviews: [], failed: true };
    });
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-6"><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Arrangement workspace</p><h1 className="mt-2 text-3xl font-bold text-[#17211d]">Arrangement reviews</h1><p className="mt-3 max-w-2xl text-sm text-[#68776f]">Check each referenced arrangement against its recorded change, then acknowledge that named review. Later changes remain separate work.</p></div>
      <nav aria-label="Review domains" className="mb-6 flex flex-wrap gap-3">
        {domains.map((domain) => <Link key={domain} href={`/arrangement-reviews?arrangement=${domain}`} aria-current={domain === selected ? "page" : undefined} className="rounded-full border border-[#cfd9d4] px-4 py-2 text-sm font-semibold text-[#0f6b5b]">{arrangementLabels[domain]} reviews</Link>)}
      </nav>
      <section aria-label="Arrangement review queue" className="space-y-4 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold text-[#17211d]">{arrangementLabels[selected]} reviews</h2><RefreshArrangementReviews /></div>
        {params.reviewed === "1" ? <p role="status" className="text-sm text-[#145c40]">The named review was marked. Other review work remains unchanged.</p> : null}
        {result.failed ? <p role="alert" className="text-sm text-[#793f27]">Arrangement reviews are temporarily unavailable. Refresh to try again.</p> : <ArrangementReviewList reviews={result.reviews} canClear />}
      </section>
    </AppShell>
  );
}
