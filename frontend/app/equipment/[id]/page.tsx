import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { formatDateTime } from "@/lib/event-requests";
import { getEquipment, getEquipmentStatus, getStatusHistory, statusLabel } from "@/lib/equipment";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { QuantityForm } from "./quantity-form";
import { StatusForm } from "./status-form";
import { StatusHistory } from "./status-history";

export default async function EquipmentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole("technical_support");
  const { id } = await params;
  const result = await getEquipment(id).then((item) => ({ item, failed: false as const })).catch((error: unknown) => {
    unstable_rethrow(error);
    return { item: null, failed: true as const };
  });

  const [statusResult, historyResult] = result.item
    ? await Promise.allSettled([getEquipmentStatus(result.item.id), getStatusHistory(result.item.id)])
    : [null, null];
  for (const settled of [statusResult, historyResult]) {
    if (settled?.status === "rejected") unstable_rethrow(settled.reason);
  }
  const availability = statusResult?.status === "fulfilled" ? statusResult.value : null;
  const history = historyResult?.status === "fulfilled" ? historyResult.value : null;

  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-4xl space-y-5">
        <Link href="/equipment" className="inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to equipment</Link>
        {result.failed ? (
          <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The equipment service is unavailable. Start the local API on port 8002, then refresh.</div>
        ) : !result.item ? (
          <h1 className="text-xl font-bold">Equipment not found</h1>
        ) : (
          <>
            <section className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h1 className="text-2xl font-bold text-[#17211d]">{result.item.type}</h1>
              <dl className="mt-5 grid gap-4 sm:grid-cols-2">
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Home location</dt><dd className="mt-1 text-sm text-[#273832]">{result.item.home_location}</dd></div>
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Operational status</dt><dd className="mt-1 text-sm text-[#273832]">{statusLabel(result.item.operational_status)}</dd></div>
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Total owned</dt><dd className="mt-1 text-sm text-[#273832]">{result.item.total_owned_quantity}</dd></div>
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Last updated</dt><dd className="mt-1 text-sm text-[#273832]">{formatDateTime(result.item.updated_at)}</dd></div>
                <div className="sm:col-span-2"><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Description</dt><dd className="mt-1 whitespace-pre-wrap text-sm text-[#273832]">{result.item.description ?? "No description"}</dd></div>
              </dl>
            </section>
            <section aria-labelledby="quantity-heading" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h2 id="quantity-heading" className="mb-4 text-lg font-bold text-[#17211d]">Quantity</h2>
              <QuantityForm equipmentId={result.item.id} quantity={result.item.total_owned_quantity} />
            </section>
            <section aria-labelledby="status-heading" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h2 id="status-heading" className="text-lg font-bold text-[#17211d]">Operational status</h2>
              <p className="mt-2 mb-4 text-sm text-[#52635c]">
                {availability
                  ? availability.available
                    ? `Available for events: ${availability.available_quantity} of ${result.item.total_owned_quantity}.`
                    : "Not available — excluded from equipment availability until it is marked Available."
                  : "Availability could not be loaded."}
              </p>
              <StatusForm equipmentId={result.item.id} currentStatus={result.item.operational_status} />
            </section>
            <section aria-labelledby="history-heading" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h2 id="history-heading" className="mb-4 text-lg font-bold text-[#17211d]">Status history</h2>
              {history ? <StatusHistory entries={history} /> : <p role="alert" className="text-sm text-[#793f27]">Status history could not be loaded.</p>}
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
