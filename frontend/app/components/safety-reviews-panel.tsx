import { formatDateTime } from "@/lib/event-requests";
import type { SafetyReview } from "@/lib/safety";

const DECISION_LABELS: Record<SafetyReview["decision"], string> = {
  approved: "Approved",
  changes_requested: "Changes requested",
  rejected: "Rejected",
};

// The Safety Officer's decisions on an event, newest first (SCRUM-60 AC4a), as
// the assigned coordinator sees them.
const FALLBACK_LABELS = {
  venue_booking: "A venue booking",
  equipment_reservation: "An equipment reservation",
} as const;

// labels maps an arrangement id to a readable name (venue and dates); ids the
// coordinator cannot resolve fall back to the arrangement kind.
export function SafetyReviewsPanel({
  reviews,
  labels = {},
}: {
  reviews: SafetyReview[];
  labels?: Record<string, string>;
}) {
  return (
    <section aria-labelledby="safety-check-heading" className="rounded-2xl border border-[#dce4e0] bg-white p-5 sm:p-6">
      <h2 id="safety-check-heading" className="text-lg font-bold text-[#1b2b25]">Safety check</h2>
      {reviews.length === 0 ? (
        <p className="mt-2 text-sm text-[#718078]">No safety decision yet.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {reviews.map((review) => (
            <li key={review.id} className="border-t border-[#eef2f0] pt-3 text-sm text-[#273832] first:border-t-0 first:pt-0">
              <p className="font-semibold">{DECISION_LABELS[review.decision]}</p>
              <p className="text-xs text-[#718078]">{formatDateTime(review.decided_at)}</p>
              {review.reason ? <p className="mt-1">{review.reason}</p> : null}
              {review.targets.length > 0 ? (
                <div className="mt-2">
                  <p className="font-semibold">To recheck:</p>
                  <ul className="ml-4 list-disc">
                    {review.targets.map((target) => (
                      <li key={`${target.arrangement}:${target.id}`}>{labels[target.id] ?? FALLBACK_LABELS[target.arrangement]}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
