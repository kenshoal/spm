import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { Suspense } from "react";
import { requireRole, type AuthenticatedUser } from "@/lib/auth";
import { coordinatorActions, getEventRequest } from "@/lib/event-requests";
import { AppShell, workspaceLinks } from "../../../components/app-shell";
import { ArrowIcon } from "../../../components/icons";
import { RequestDetails } from "../../../components/request-details";
import { TransitionButton } from "./transition-buttons";

async function CoordinatorRequestView({ id }: { id: string }) {
  const result = await getEventRequest(id)
    .then((request) => ({ request, failed: false as const }))
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

  const request = result.request;
  return (
    <div className="mx-auto max-w-4xl">
      <Link href="/coordination/requests" className="mb-5 inline-flex items-center gap-1 text-sm font-semibold text-[#0f6b5b] hover:underline"><ArrowIcon className="size-4 rotate-180" /> Back to assigned requests</Link>
      <RequestDetails request={request} />
      <Link
        href={`/venues/search${request.expected_attendance ? `?required_capacity=${request.expected_attendance}` : ""}`}
        className="mt-5 inline-flex min-h-11 items-center rounded-xl border border-[#cfd9d4] bg-white px-4 text-sm font-semibold text-[#0f6b5b] hover:bg-[#f4f7f5]"
      >
        Find venues for this event
      </Link>
      <section aria-label="Coordinator actions" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
        <h2 className="text-lg font-bold text-[#17211d]">Actions</h2>
        {coordinatorActions(request.status).length === 0 ? (
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
  return <div aria-label="Loading request" className="mx-auto h-[34rem] max-w-4xl animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />;
}

export default async function CoordinationRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const user: AuthenticatedUser = await requireRole("event_coordinator");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <Suspense fallback={<DetailLoading />}>
        {params.then(({ id }) => <CoordinatorRequestView id={id} />)}
      </Suspense>
    </AppShell>
  );
}
