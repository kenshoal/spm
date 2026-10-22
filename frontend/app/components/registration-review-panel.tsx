"use client";

import { useActionState, useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import type { RegistrationReview } from "@/lib/registration-reviews";
import { acknowledgeRegistrationReview, type RegistrationReviewState } from "../coordination/actions";

const initialState: RegistrationReviewState = {};
const dateFormat = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore",
});

function RegistrationAcknowledgement({ eventRequestId, reviewId }: { eventRequestId: string; reviewId: string }) {
  const [checked, setChecked] = useState(false);
  const checkboxId = useId();
  const router = useRouter();
  const [state, action, pending] = useActionState(
    acknowledgeRegistrationReview.bind(null, eventRequestId, reviewId), initialState,
  );
  useEffect(() => {
    if (state.acknowledged) router.refresh();
  }, [state.acknowledged, router]);
  return (
    <form action={action} className="mt-4 space-y-3 border-t border-[#e3ebe7] pt-4">
      <label htmlFor={checkboxId} className="flex items-start gap-3 text-sm text-[#34463f]">
        <input id={checkboxId} name="reviewed" type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} disabled={pending || state.acknowledged} className="mt-1 size-4" />
        I have checked the registration arrangements against this change
      </label>
      <button type="submit" disabled={!checked || pending || state.acknowledged} className="min-h-11 rounded-lg bg-[#0f6b5b] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60">
        {pending ? "Saving…" : "Acknowledge registration review"}
      </button>
      {state.message ? <p role="alert" className="text-sm text-[#8e3d35]">{state.message}</p> : null}
    </form>
  );
}

/** Retained causes stay visible after acknowledgement; no attendee changes occur. */
export function RegistrationReviewPanel({ eventRequestId, reviews, canAcknowledge = false }: {
  eventRequestId: string; reviews: RegistrationReview[]; canAcknowledge?: boolean;
}) {
  return (
    <section aria-label="Registration reviews" className="mt-5 space-y-4 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Registration reviews</h2>
      <p className="text-sm text-[#526159]">These checks concern registration arrangements. Acknowledgement does not change attendees, capacity or registration windows.</p>
      {reviews.length === 0 ? <p className="text-sm text-[#68776f]">No registration reviews</p> : reviews.map((review) => (
        <article key={review.id} className="rounded-xl border border-[#dce4e0] p-4">
          <h3 className="font-semibold">{review.cleared_at ? "Acknowledged" : "Outstanding"}</h3>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm">{review.reason}</p>
          <p className="mt-2 text-xs text-[#68776f]">Raised <time dateTime={review.raised_at}>{dateFormat.format(new Date(review.raised_at))}</time></p>
          <p className="mt-1 break-all text-xs text-[#68776f]">Review reference: {review.id}</p>
          {review.cleared_at ? <p className="mt-2 break-words text-sm">Acknowledged by coordinator {review.cleared_by} · <time dateTime={review.cleared_at}>{dateFormat.format(new Date(review.cleared_at))}</time></p> : null}
          {canAcknowledge && !review.cleared_at ? <RegistrationAcknowledgement eventRequestId={eventRequestId} reviewId={review.id} /> : null}
        </article>
      ))}
    </section>
  );
}
