import { blockReasonText, type VenueBlock } from "@/lib/venue-block-options";

function formatDate(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

// Every recorded block, including lifted ones, so staff can see the history.
export function BlockList({ blocks }: { blocks: VenueBlock[] }) {
  const sorted = [...blocks].sort((a, b) => a.start_date.localeCompare(b.start_date));
  return (
    <section className="rounded-2xl border border-[#dce4e0] bg-white p-6">
      <h2 id="recorded-blocks" className="mb-3 text-lg font-bold text-[#1b2b25]">Recorded blocks</h2>
      {sorted.length === 0 ? (
        <p className="text-sm text-[#718078]">No blocks recorded for this venue.</p>
      ) : (
        <ul aria-labelledby="recorded-blocks" className="space-y-2">
          {sorted.map((block) => (
            <li key={block.id} className="rounded-xl border border-[#eef2f0] px-4 py-3 text-sm text-[#273832]">
              <span className="font-semibold">{formatDate(block.start_date)} – {formatDate(block.end_date)}</span>
              {" · "}{block.slots.join(", ")}
              {" · "}{blockReasonText(block)}
              {" · "}
              <span className={block.status === "active" ? "font-bold text-[#8c3a2b]" : "text-[#718078]"}>{block.status === "active" ? "Active" : "Lifted"}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
