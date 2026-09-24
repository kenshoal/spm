import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { listAwaitingAssignment, listCoordinators, listCurrentAssignments } from "@/lib/operations";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { AssignedList, AwaitingList } from "./assignment-lists";

async function AssignmentData() {
  const [awaiting, assigned, coordinators] = await Promise.allSettled([
    listAwaitingAssignment(),
    listCurrentAssignments(),
    listCoordinators(),
  ]);
  if (awaiting.status === "rejected" || assigned.status === "rejected") {
    return (
      <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8">
        <p className="font-semibold text-[#793f27]">The event request service is unavailable.</p>
        <p className="mt-2 text-sm leading-6 text-[#8b604d]">Start the local API on port 8003, then refresh this page.</p>
      </div>
    );
  }
  const people = coordinators.status === "fulfilled" ? coordinators.value : [];
  return (
    <div className="space-y-10">
      {coordinators.status === "rejected" ? (
        <p role="alert" className="rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">The coordinator directory is unavailable, so assignments can&apos;t be made right now. Start the auth service on port 8001, then refresh.</p>
      ) : null}
      <section aria-labelledby="awaiting-heading">
        <h2 id="awaiting-heading" className="mb-4 text-xl font-bold text-[#17211d]">Awaiting a coordinator ({awaiting.value.length})</h2>
        <AwaitingList requests={awaiting.value} coordinators={people} />
      </section>
      <section aria-labelledby="assigned-heading">
        <h2 id="assigned-heading" className="mb-4 text-xl font-bold text-[#17211d]">Assigned ({assigned.value.length})</h2>
        <AssignedList assignments={assigned.value} coordinators={people} />
      </section>
    </div>
  );
}

function Loading() {
  return <div aria-label="Loading assignments" className="space-y-3">{[1, 2].map((item) => <div key={item} className="h-36 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />)}</div>;
}

export default async function AssignmentsPage() {
  const user = await requireRole("event_operations_manager");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Operations workspace</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Coordinator assignments</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Give each submitted request a coordinator, or hand an in-progress request to someone else.</p>
      </div>
      <Suspense fallback={<Loading />}>
        <AssignmentData />
      </Suspense>
    </AppShell>
  );
}
