import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { Suspense } from "react";
import { requireRole, type AuthenticatedUser } from "@/lib/auth";
import {
  coordinatorActions,
  getEventRequestStatusView,
  listEventChangeRequests,
  listReviewDecisions,
} from "@/lib/event-requests";
import { AppShell, workspaceLinks } from "../../../components/app-shell";
import { ArrowIcon } from "../../../components/icons";
import { RequestDetails } from "../../../components/request-details";
import { ArrangementReviewPanel, ArrangementReviewLoading } from "../../../components/arrangement-review-panel";
import { RegistrationReviews, RegistrationReviewsLoading } from "../../../components/registration-reviews";
import { RegistrationInfoLoading, RegistrationInfoPanel } from "../../../components/registration-info";
import { isEventDay } from "@/lib/registration-info";
import { ReviewDecisionHistory } from "../../../components/review-decision-history";
import { SafetyReviewsPanel } from "../../../components/safety-reviews-panel";
import { listSafetyReviews } from "@/lib/safety";
import { formatBookingDates, listEventBookings } from "@/lib/event-bookings";
import { listVenues } from "@/lib/venues";
import { SUPPORT_STATUSES } from "@/lib/technical-support";
import { ReviewDecisionPanel } from "./review-decision-panel";
import { TransitionButton } from "./transition-buttons";
import { ChangeRequestPanel } from "./change-request-panel";
import { VenueBookingsLoading, VenueBookingsPanel } from "./venue-bookings-panel";
import { TechnicalSupportLoading, TechnicalSupportPanel } from "./technical-support-panel";

import { StatusHistory, StatusHistoryLoading } from '../../../components/status-history';

async function CoordinatorRequestView({ id, currentUserId }: { id: string; currentUserId: string }) {
  const result = await getEventRequestStatusView(id)
    .then((view) => ({ ...view, failed: false as const }))
    .catch((error: unknown) => {
      unstable_rethrow(error);
      return { request: null, failed: true as const };
    });

  if (result.failed) {
    return <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The event request service is unavailable. Start the local API on port 8003, then refresh.</div>;
  }
  if (!result.request) {
    return <div className="rounded-2xl border border-[#dce4e0] bg-white px-6 py-12 text-center"><h1 className="text-xl font-bold">Request not found</h1><p className="mt-2 text-sm text-[#718078]">It may not exist, or it may not be assigned to you.</p></div>;
  }

  if (result.statusUnsettled) {
    return (
      <div className="mx-auto max-w-4xl">
        <p role="alert" className="mb-5 rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">This request changed while loading. Refresh to see its current status and available actions.</p>
        <RequestDetails request={result.request} />
        <StatusHistory entries={[]} unavailable />
      </div>
    );
  }

  const request = result.request;
  const [decisionResult, changeResult, safetyResult, bookingLabels] = await Promise.all([
    listReviewDecisions(id)
      .then((decisions) => ({ decisions, failed: false as const }))
      .catch(() => ({ decisions: [], failed: true as const })),
    listEventChangeRequests(id)
      .then((requests) => ({ requests, failed: false as const }))
      .catch(() => ({ requests: [], failed: true as const })),
    listSafetyReviews(id)
      .then((reviews) => ({ reviews, failed: false as const }))
      .catch(() => ({ reviews: [], failed: true as const })),
    // Names for the bookings a Safety Officer asked to recheck; the panel falls
    // back to "A venue booking" if they cannot be loaded.
    Promise.all([listEventBookings(id), listVenues()])
      .then(([bookings, venues]) => {
        const names = new Map(venues.map((venue) => [venue.id, venue.name]));
        return Object.fromEntries(
          bookings.map((booking) => [
            booking.id,
            `${names.get(booking.venue_id) ?? "Venue"}, ${formatBookingDates(booking.start_date, booking.end_date)}`,
          ]),
        );
      })
      .catch(() => ({}) as Record<string, string>),
  ]);
  const decisions = decisionResult.decisions;
  const latestClarification = decisions.find(
    (decision) => decision.decision_status === "Changes Requested",
  );
  const canResumeReview =
    !decisionResult.failed &&
    request.status === "Changes Requested" &&
    Boolean(latestClarification?.organiser_response);
  const awaitingClarification =
    !decisionResult.failed &&
    request.status === "Changes Requested" &&
    Boolean(latestClarification) &&
    !latestClarification?.organiser_response;
  return (
    <div className="mx-auto max-w-4xl">
      <Link href="/coordination/requests" className="mb-5 inline-flex items-center gap-1 text-sm font-semibold text-[#0f6b5b] hover:underline"><ArrowIcon className="size-4 rotate-180" /> Back to assigned requests</Link>
      <RequestDetails request={request} coordinatorAssigned />
      <StatusHistory entries={result.history} unavailable={result.historyUnavailable} />
      <Suspense fallback={<ArrangementReviewLoading />}><ArrangementReviewPanel eventId={id} /></Suspense>
      <Suspense fallback={<RegistrationReviewsLoading />}><RegistrationReviews eventRequestId={id} canAcknowledge /></Suspense>
      <Suspense fallback={<RegistrationInfoLoading />}><RegistrationInfoPanel eventRequestId={id} canAddAttendee={request.status === "Confirmed"} canCheckIn={request.status === "Confirmed" && isEventDay(request.proposed_date_times)} /></Suspense>
      <div className="mt-5">
        <ReviewDecisionHistory decisions={decisions} unavailable={decisionResult.failed} />
      </div>
      {changeResult.failed ? <div role="alert" className="mt-5 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Change requests are temporarily unavailable. Decisions are disabled until they can be loaded.</div> : <ChangeRequestPanel requests={changeResult.requests} eventStatus={request.status} />}
      {safetyResult.failed ? (
        <div role="alert" className="mt-5 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">The safety check is temporarily unavailable.</div>
      ) : request.status === "Safety Review" || safetyResult.reviews.length > 0 ? (
        <div className="mt-5">
          <SafetyReviewsPanel reviews={safetyResult.reviews} labels={bookingLabels} />
        </div>
      ) : null}
      <Suspense fallback={<VenueBookingsLoading />}>
        <VenueBookingsPanel eventRequestId={request.id} />
      </Suspense>
      {(SUPPORT_STATUSES as readonly string[]).includes(request.status) ? (
        <Suspense fallback={<TechnicalSupportLoading />}>
          <TechnicalSupportPanel
            eventRequestId={request.id}
            status={request.status}
            currentUserId={currentUserId}
          />
        </Suspense>
      ) : null}
      <Link
        href={`/venues/search${request.expected_attendance ? `?required_capacity=${request.expected_attendance}` : ""}`}
        className="mt-5 inline-flex min-h-11 items-center rounded-xl border border-[#cfd9d4] bg-white px-4 text-sm font-semibold text-[#0f6b5b] hover:bg-[#f4f7f5]"
      >
        Find venues for this event
      </Link>
      <section aria-label="Coordinator actions" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
        <h2 className="text-lg font-bold text-[#17211d]">Actions</h2>
        {request.status === "Under Review" && !decisionResult.failed ? (
          <ReviewDecisionPanel eventRequestId={request.id} />
        ) : null}
        {awaitingClarification ? (
          <p className="mt-3 text-sm leading-6 text-[#526159]">Waiting for the organiser to send a clarification response.</p>
        ) : null}
        {canResumeReview ? (
          <div className="mt-4">
            <p className="mb-3 text-sm leading-6 text-[#526159]">The organiser has responded. Continue the review to make a new decision.</p>
            <TransitionButton eventRequestId={request.id} kind="resume-review" />
          </div>
        ) : null}
        {coordinatorActions(request.status).length === 0 && !canResumeReview ? (
          <p className="mt-3 text-sm leading-6 text-[#718078]">This request is {request.status.toLowerCase()} — no further actions are available.</p>
        ) : (
          <div className="mt-4 flex flex-wrap gap-3">
            {coordinatorActions(request.status).map((kind) => (
              <TransitionButton key={kind} eventRequestId={request.id} kind={kind} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function DetailLoading() {
  return <><div aria-label="Loading request" className="mx-auto h-[34rem] max-w-4xl animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" /><StatusHistoryLoading /></>;
}

export default async function CoordinationRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const user: AuthenticatedUser = await requireRole("event_coordinator");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <Suspense fallback={<DetailLoading />}>
        {params.then(({ id }) => <CoordinatorRequestView id={id} currentUserId={user.id} />)}
      </Suspense>
    </AppShell>
  );
}
