import { arrangementLabels, type ArrangementReview } from "@/lib/arrangement-reviews";
import { formatDateTime } from "@/lib/event-requests";
import { ClearReviewForm } from "../arrangement-reviews/clear-review-form";

const causeLabels: Record<ArrangementReview["trigger_type"], string> = {
  event_change: "Event change",
  equipment_unavailable: "Equipment unavailable",
  safety_recheck: "Safety recheck",
  venue_timing_change: "Venue timing change",
  venue_block: "Venue blocked",
};

export function ArrangementReviewList({ reviews, canClear = false }: { reviews: ArrangementReview[]; canClear?: boolean }) {
  if (reviews.length === 0) return <p className="text-sm text-[#68776f]">No outstanding arrangement reviews</p>;
  return (
    <ul className="space-y-4">
      {reviews.map((review) => (
        <li key={review.id} className="rounded-xl border border-[#dce4e0] bg-white p-4 sm:p-5">
          <h3 className="font-bold text-[#17211d]">{arrangementLabels[review.arrangement]} review</h3>
          <p className="mt-1 break-all text-xs text-[#68776f]">Arrangement reference: {review.arrangement_id}</p>
          <p className="mt-1 break-all text-xs text-[#68776f]">Event reference: {review.event_request_id}</p>
          <p className="mt-3 whitespace-pre-wrap break-words text-sm text-[#273832]">{review.reason}</p>
          <p className="mt-2 text-xs text-[#68776f]">{causeLabels[review.trigger_type]} · <time dateTime={review.raised_at}>{formatDateTime(review.raised_at)}</time></p>
          <p className="mt-1 break-all text-xs text-[#68776f]">Cause reference: {review.trigger_id}</p>
          {canClear ? <ClearReviewForm reviewId={review.id} arrangement={review.arrangement} /> : null}
        </li>
      ))}
    </ul>
  );
}
