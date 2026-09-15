import Link from "next/link";
import { Suspense } from "react";
import { getEventRequest } from "@/lib/event-requests";
import { AppShell } from "../../../components/app-shell";
import { ArrowIcon } from "../../../components/icons";
import { EventRequestForm } from "../../new/event-request-form";

async function EditDraft({ id }: { id: string }) {
  const result = await getEventRequest(id)
    .then((request) => ({ request, failed: false as const }))
    .catch(() => ({ request: null, failed: true as const }));

  if (result.failed) {
    return <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The event request service is unavailable. Start the local API on port 8003, then refresh.</div>;
  }
  if (!result.request) {
    return <div className="rounded-2xl border border-[#dce4e0] bg-white px-6 py-12 text-center"><h1 className="text-xl font-bold">Draft not found</h1><p className="mt-2 text-sm text-[#718078]">It may belong to another organiser or have been deleted.</p></div>;
  }
  if (result.request.status !== "Draft") {
    return <div className="rounded-2xl border border-[#dce4e0] bg-white px-6 py-12 text-center"><h1 className="text-xl font-bold">This request is read-only</h1><p className="mt-2 text-sm text-[#718078]">Only Draft requests can be updated.</p><Link href="/event-requests" className="mt-5 inline-flex rounded-xl bg-[#0f6b5b] px-5 py-3 text-sm font-bold text-white">Back to drafts</Link></div>;
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
    </div>
  );
}

function EditLoading() {
  return <div aria-label="Loading draft" className="mx-auto h-[34rem] max-w-4xl animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />;
}

export default function EditEventRequestPage({ params }: { params: Promise<{ id: string }> }) {
  return <AppShell><Suspense fallback={<EditLoading />}>{params.then(({ id }) => <EditDraft id={id} />)}</Suspense></AppShell>;
}
