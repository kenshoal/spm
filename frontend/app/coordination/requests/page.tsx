import { unstable_rethrow } from "next/navigation";
import { Suspense } from "react";
import { requireRole, type AuthenticatedUser } from "@/lib/auth";
import { listAssignedEventRequests } from "@/lib/event-requests";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { CoordinationRequestList } from "./coordination-request-list";

async function AssignedRequestData() {
  const result = await listAssignedEventRequests()
    .then((requests) => ({ requests, failed: false as const }))
    .catch((error: unknown) => {
      unstable_rethrow(error);
      return { requests: [], failed: true as const };
    });

  if (result.failed) {
    return (
      <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8">
        <p className="font-semibold text-[#793f27]">The event request service is unavailable.</p>
        <p className="mt-2 text-sm leading-6 text-[#8b604d]">Start the local API on port 8003, then refresh this page.</p>
      </div>
    );
  }
  return <CoordinationRequestList requests={result.requests} />;
}

function ListLoading() {
  return <div aria-label="Loading assigned requests" className="space-y-3">{[1, 2].map((item) => <div key={item} className="h-36 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />)}</div>;
}

export default async function CoordinationRequestsPage() {
  const user: AuthenticatedUser = await requireRole("event_coordinator");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Coordinator workspace</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Requests assigned to you</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Review the events you are coordinating and keep their status up to date.</p>
      </div>
      <Suspense fallback={<ListLoading />}>
        <AssignedRequestData />
      </Suspense>
    </AppShell>
  );
}
