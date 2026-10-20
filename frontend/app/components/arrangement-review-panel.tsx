import { unstable_rethrow } from "next/navigation";
import { listEventArrangementReviews } from "@/lib/arrangement-reviews";
import { ArrangementReviewList } from "./arrangement-review-list";
import { RefreshArrangementReviews } from "./refresh-arrangement-reviews";

export async function ArrangementReviewPanel({ eventId }: { eventId: string }) {
  const result = await listEventArrangementReviews(eventId)
    .then((reviews) => ({ reviews, failed: false }))
    .catch((error: unknown) => {
      unstable_rethrow(error);
      return { reviews: [], failed: true };
    });
  return (
    <section aria-label="Outstanding arrangement reviews" className="mt-5 space-y-4 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold text-[#17211d]">Outstanding arrangement reviews</h2><RefreshArrangementReviews /></div>
      {result.failed ? <p role="alert" className="text-sm text-[#793f27]">Arrangement reviews are temporarily unavailable. Refresh to try again.</p> : <ArrangementReviewList reviews={result.reviews} />}
    </section>
  );
}
export function ArrangementReviewLoading() {
  return <p role="status" className="mt-5 p-6 text-sm text-[#68776f]">Loading arrangement reviews…</p>;
}
