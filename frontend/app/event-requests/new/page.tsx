import Link from "next/link";
import { AppShell } from "../../components/app-shell";
import { ArrowIcon } from "../../components/icons";
import { EventRequestForm } from "./event-request-form";

export default function NewEventRequestPage() {
  return (
    <AppShell signedIn>
      <div className="mx-auto max-w-4xl">
        <Link href="/event-requests" className="mb-5 inline-flex items-center gap-1 text-sm font-semibold text-[#0f6b5b] hover:underline">
          <ArrowIcon className="size-4 rotate-180" /> Back to event requests
        </Link>
        <div className="mb-8">
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">New request</p>
          <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Create an event request</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Add what you know now and save it as a draft. You can return to complete the remaining details later.</p>
        </div>
        <EventRequestForm />
      </div>
    </AppShell>
  );
}
