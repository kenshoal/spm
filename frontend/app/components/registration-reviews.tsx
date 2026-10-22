import { unstable_rethrow } from "next/navigation";
import { listRegistrationReviews } from "@/lib/registration-reviews";
import { RegistrationReviewPanel } from "./registration-review-panel";

/** Server-only read keeps tokens out of the interactive evidence component. */
export async function RegistrationReviews({ eventRequestId, canAcknowledge = false }: {
  eventRequestId: string; canAcknowledge?: boolean;
}) {
  let reviews;
  try {
    reviews = await listRegistrationReviews(eventRequestId);
  } catch (error) {
    unstable_rethrow(error);
    return <section aria-label="Registration reviews" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6"><h2 className="text-lg font-bold">Registration reviews</h2><p role="alert" className="mt-3 text-sm text-[#793f27]">Registration reviews are temporarily unavailable. Refresh to try again.</p></section>;
  }
  return <RegistrationReviewPanel eventRequestId={eventRequestId} reviews={reviews} canAcknowledge={canAcknowledge} />;
}

export function RegistrationReviewsLoading() {
  return <p role="status" className="mt-5 p-6 text-sm text-[#68776f]">Loading registration reviews…</p>;
}
