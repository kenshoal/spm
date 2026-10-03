import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { requireRole } from "@/lib/auth";
import { isOperationalStatus, listEquipment, OPERATIONAL_STATUSES, statusLabel } from "@/lib/equipment";
import { AppShell, workspaceLinks } from "../components/app-shell";

export default async function EquipmentPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const user = await requireRole("technical_support");
  const requested = (await searchParams).status ?? "";
  const status = isOperationalStatus(requested) ? requested : undefined;
  const result = await listEquipment(status).then((items) => ({ items, failed: false as const })).catch((error: unknown) => {
    unstable_rethrow(error);
    return { items: [], failed: true as const };
  });

  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Technical support workspace</p>
          <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Equipment catalogue</h1>
        </div>
        <Link href="/equipment/new" className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d]">+ Add equipment</Link>
      </div>
      <form method="get" className="mb-5 flex items-end gap-3">
        <label className="text-sm font-semibold text-[#34463f]">Show
          <select name="status" defaultValue={status ?? ""} className="mt-1 block min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm">
            <option value="">All statuses</option>
            {OPERATIONAL_STATUSES.map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
          </select>
        </label>
        <button type="submit" className="min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-4 text-sm font-semibold text-[#0f6b5b]">Filter</button>
      </form>
      {result.failed ? (
        <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The equipment service is unavailable. Start the local API on port 8002, then refresh.</div>
      ) : result.items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No equipment matches. Add equipment to the catalogue.</p>
      ) : (
        <div className="space-y-3">
          {result.items.map((item) => (
            <article key={item.id} aria-labelledby={`equipment-${item.id}`} className="flex flex-col gap-2 rounded-2xl border border-[#dce4e0] bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 id={`equipment-${item.id}`} className="text-lg font-bold text-[#1b2b25]">{item.type}</h2>
                <p className="text-sm text-[#68776f]">{item.total_owned_quantity} owned · {item.home_location} · {statusLabel(item.operational_status)}</p>
              </div>
              <Link href={`/equipment/${item.id}`} className="text-sm font-semibold text-[#0f6b5b] hover:underline">Open {item.type}</Link>
            </article>
          ))}
        </div>
      )}
    </AppShell>
  );
}
