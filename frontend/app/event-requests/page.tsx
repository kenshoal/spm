import { Suspense } from "react";
import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { groupRequests, listEventRequests, type RequestFilter } from "@/lib/event-requests";
import { AppShell, workspaceLinks } from "../components/app-shell";
import { RequestList } from "./request-list";
import { RequestTabs } from "./request-tabs";

const validFilters = new Set<RequestFilter>(["all", "draft", "submitted", "in-progress", "completed"]);

async function RequestData({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const requestedFilter = (await searchParams).status;
  const filter: RequestFilter = validFilters.has(requestedFilter as RequestFilter)
    ? requestedFilter as RequestFilter
    : "all";
  const result = await listEventRequests()
    .then((requests) => ({ requests, failed: false as const }))
    .catch(() => ({ requests: [], failed: true as const }));

  if (result.failed) {
    return (
      <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8">
        <p className="font-semibold text-[#793f27]">The event request service is unavailable.</p>
        <p className="mt-2 text-sm leading-6 text-[#8b604d]">Start the local API on port 8003, then refresh this page.</p>
      </div>
    );
  }
  const groups = groupRequests(result.requests);
  const counts = {
    all: groups.all.length,
    draft: groups.draft.length,
    submitted: groups.submitted.length,
    "in-progress": groups["in-progress"].length,
    completed: groups.completed.length,
  };
  const emptyMessages: Record<RequestFilter, string> = {
    all: "Create an event request to get started.",
    draft: "Your saved drafts will appear here.",
    submitted: "Submitted requests will appear here.",
    "in-progress": "Requests being coordinated will appear here.",
    completed: "Completed events will appear here after coordination finishes.",
  };
  return (
    <>
      <RequestTabs selected={filter} counts={counts} />
      <RequestList requests={groups[filter]} emptyMessage={emptyMessages[filter]} />
    </>
  );
}

function ListLoading() {
  return <div aria-label="Loading event requests" className="space-y-3">{[1, 2].map((item) => <div key={item} className="h-36 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />)}</div>;
}

export default async function EventRequestsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const user = await requireRole("event_organiser");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Organiser workspace</p>
          <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Your event requests</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Start a request, save incomplete details and return to finish the draft later.</p>
        </div>
        <Link href="/event-requests/new" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white shadow-sm transition hover:bg-[#0b5b4d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b]">
          <span aria-hidden="true" className="text-lg leading-none">+</span>
          Create new
        </Link>
      </div>
      <Suspense fallback={<ListLoading />}>
        <RequestData searchParams={searchParams} />
      </Suspense>
    </AppShell>
  );
}
