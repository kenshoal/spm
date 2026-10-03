import {
  formatDateTime,
  type EventReviewDecision,
} from "@/lib/event-requests";

export function ReviewDecisionHistory({
  decisions,
  unavailable = false,
}: {
  decisions: EventReviewDecision[];
  unavailable?: boolean;
}) {
  if (unavailable) {
    return (
      <section
        role="alert"
        aria-label="Review activity unavailable"
        className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] p-6 text-sm leading-6 text-[#793f27] sm:p-7"
      >
        Review activity could not be loaded. Refresh the page before continuing
        with this review.
      </section>
    );
  }

  if (decisions.length === 0) return null;

  return (
    <section
      aria-label="Review activity"
      className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7"
    >
      <h2 className="text-lg font-bold text-[#17211d]">Review activity</h2>
      <ol className="mt-5 space-y-4">
        {decisions.map((decision) => (
          <li key={decision.id} className="border-l-2 border-[#9fc7ba] pl-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold text-[#273832]">{decision.decision_status}</p>
              <time className="text-xs text-[#718078]" dateTime={decision.decided_at}>
                {formatDateTime(decision.decided_at)}
              </time>
            </div>
            {decision.reason ? (
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#526159]">
                {decision.reason}
              </p>
            ) : null}
            {decision.organiser_response ? (
              <div className="mt-3 rounded-lg bg-[#f1f5f3] px-3 py-2">
                <p className="text-xs font-bold uppercase tracking-wide text-[#526159]">Organiser response</p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[#273832]">{decision.organiser_response}</p>
                {decision.responded_at ? (
                  <time className="mt-1 block text-xs text-[#718078]" dateTime={decision.responded_at}>
                    Sent {formatDateTime(decision.responded_at)}
                  </time>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
