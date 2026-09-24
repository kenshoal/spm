import { formatDateTime } from "@/lib/event-requests";
import type { StatusHistoryEntry } from "@/lib/equipment";
import { statusLabel } from "@/lib/equipment-options";

export function StatusHistory({ entries }: { entries: StatusHistoryEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-[#718078]">No status changes recorded yet.</p>;
  return (
    <ol className="space-y-3">
      {entries.map((entry) => (
        <li key={entry.id} className="rounded-xl border border-[#edf1ef] px-4 py-3 text-sm text-[#273832]">
          <p className="font-semibold">{entry.old_status ? `${statusLabel(entry.old_status)} → ` : ""}{statusLabel(entry.new_status)}</p>
          {entry.reason ? <p className="mt-1 text-[#52635c]">{entry.reason}</p> : null}
          <p className="mt-1 text-xs text-[#718078]">By {entry.changed_by} · {formatDateTime(entry.changed_at)}</p>
        </li>
      ))}
    </ol>
  );
}
