import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import {
  getCoordinatorAssignment,
  getEventRequestStatusView,
  listEventChangeRequests,
  listReviewDecisions,
} from "@/lib/event-requests";
import { AppShell, workspaceLinks } from "../../../components/app-shell";
import { ArrowIcon } from "../../../components/icons";
import { EventRequestForm } from "../../new/event-request-form";
import { RequestDetails } from "../../../components/request-details";
import { ReviewDecisionHistory } from "../../../components/review-decision-history";
import { ClarificationResponseForm } from "../clarification-response-form";
import { ChangeRequestHistory } from "../../../components/change-request-history";
import { RegistrationReviews, RegistrationReviewsLoading } from "../../../components/registration-reviews";
import { ChangeRequestDialog } from "../change-request-dialog";

import { StatusHistory, StatusHistoryLoading } from '../../../components/status-history';

const SHARED_NOTICE = "Shared by another organiser in your organisation. You can view it but not change it.";

async function EditDraft({ id, viewerId }: { id: string; viewerId: string }) {
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
    return <div className="rounded-2xl border border-[#dce4e0] bg-white px-6 py-12 text-center"><h1 className="text-xl font-bold">Draft not found</h1><p className="mt-2 text-sm text-[#718078]">It may belong to another organiser or have been deleted.</p></div>;
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

  // SCRUM-39: same-organisation colleagues get a read-only view.
  const shared = result.request.organiser_id !== viewerId;
  if (result.request.status === "Changes Requested") {
    const decisionResult = await listReviewDecisions(id)
      .then((decisions) => ({ decisions, failed: false as const }))
      .catch(() => ({ decisions: [], failed: true as const }));
    const decisions = decisionResult.decisions;
    const latestClarification = decisions.find(
      (decision) => decision.decision_status === "Changes Requested",
    );
    return (
      <div className="mx-auto max-w-4xl">
        <Link href="/event-requests" className="mb-5 inline-flex items-center gap-1 text-sm font-semibold text-[#0f6b5b] hover:underline"><ArrowIcon className="size-4 rotate-180" /> Back to event requests</Link>
        <div className="mb-6 rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">{shared ? SHARED_NOTICE : "Your coordinator requested clarification. The submitted request remains read-only; respond below so review can continue."}</div>
        <RequestDetails request={result.request} coordinatorAssigned />
        <StatusHistory entries={result.history} unavailable={result.historyUnavailable} />
        {!shared ? <Suspense fallback={<RegistrationReviewsLoading />}><RegistrationReviews eventRequestId={id} /></Suspense> : null}
        <div className="mt-5"><ReviewDecisionHistory decisions={decisions} unavailable={decisionResult.failed} /></div>
        <div className="mt-5">
          {decisionResult.failed || shared ? null : latestClarification?.organiser_response ? (
            <div role="status" className="rounded-xl border border-[#bcd9ce] bg-[#edf7f3] px-4 py-3 text-sm text-[#145c40]">Your response was sent. The assigned coordinator can now continue the review.</div>
          ) : (
            <ClarificationResponseForm eventRequestId={id} />
          )}
        </div>
      </div>
    );
  }
  if (result.request.status !== "Draft") {
    const [coordinatorAssigned, decisionResult, changeResult] = await Promise.all([
      getCoordinatorAssignment(id)
        .then((assignment) => assignment !== null)
        // Keep the status view available if assignment lookup is temporarily unavailable.
        .catch(() => undefined),
      listReviewDecisions(id)
        .then((decisions) => ({ decisions, failed: false as const }))
        .catch(() => ({ decisions: [], failed: true as const })),
      listEventChangeRequests(id)
        .then((requests) => ({ requests, failed: false as const }))
        .catch(() => ({ requests: [], failed: true as const })),
    ]);
    const hasPendingChange = changeResult.requests.some((change) => change.status === "Pending");
    const canRequestChange = (result.request.status === "Approved" || result.request.status === "Planning")
      && !shared && !hasPendingChange && !changeResult.failed;
    return (
      <div className="mx-auto max-w-4xl">
        <Link href="/event-requests" className="mb-5 inline-flex items-center gap-1 text-sm font-semibold text-[#0f6b5b] hover:underline"><ArrowIcon className="size-4 rotate-180" /> Back to event requests</Link>
        <div className="mb-6 rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">{shared ? SHARED_NOTICE : "This request is read-only after submission."}</div>
        <RequestDetails
          request={result.request}
          coordinatorAssigned={coordinatorAssigned}
          action={canRequestChange ? <ChangeRequestDialog eventRequestId={id} /> : null}
        />
        <StatusHistory entries={result.history} unavailable={result.historyUnavailable} />
        {!shared ? <Suspense fallback={<RegistrationReviewsLoading />}><RegistrationReviews eventRequestId={id} /></Suspense> : null}
        <div className="mt-5"><ReviewDecisionHistory decisions={decisionResult.decisions} unavailable={decisionResult.failed} /></div>
        <div>
          {changeResult.failed ? (
            <div role="alert" className="mt-5 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Change request history is temporarily unavailable.</div>
          ) : (
            <div className="mt-5"><ChangeRequestHistory requests={changeResult.requests} /></div>
          )}
          {hasPendingChange ? <div role="status" className="mt-5 rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">A change request is saved for the assigned coordinator to review. The event plan remains unchanged while the proposal is Pending.</div> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <Link href="/event-requests" className="mb-5 inline-flex items-center gap-1 text-sm font-semibold text-[#0f6b5b] hover:underline"><ArrowIcon className="size-4 rotate-180" /> Back to drafts</Link>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Draft request</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Continue your event request</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Update any available details and save this draft again.</p>
      </div>
      <EventRequestForm request={result.request} />
      <StatusHistory entries={result.history} unavailable={result.historyUnavailable} />
    </div>
  );
}

function EditLoading() {
  return <><div aria-label="Loading draft" className="mx-auto h-[34rem] max-w-4xl animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" /><StatusHistoryLoading /></>;
}

export default async function EditEventRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole("event_organiser");
  return <AppShell signedIn navLinks={workspaceLinks(user.roles)}><Suspense fallback={<EditLoading />}>{params.then(({ id }) => <EditDraft id={id} viewerId={user.id} />)}</Suspense></AppShell>;
}
