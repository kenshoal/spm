import Link from "next/link";
import type { RequestFilter } from "@/lib/event-requests";

const tabs: Array<{ value: RequestFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "submitted", label: "Submitted" },
  { value: "in-progress", label: "In Progress" },
  { value: "completed", label: "Completed" },
];

export function RequestTabs({
  selected,
  counts,
}: {
  selected: RequestFilter;
  counts: Record<RequestFilter, number>;
}) {
  return (
    <nav aria-label="Filter event requests" className="mb-5 flex gap-2 overflow-x-auto border-b border-[#dce4e0]">
      {tabs.map((tab) => {
        const active = selected === tab.value;
        const href = tab.value === "all" ? "/event-requests" : `/event-requests?status=${tab.value}`;
        return (
          <Link
            key={tab.value}
            href={href}
            aria-label={`${tab.label} (${counts[tab.value]})`}
            aria-current={active ? "page" : undefined}
            className={`flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold ${active ? "border-[#0f6b5b] text-[#0f6b5b]" : "border-transparent text-[#68776f] hover:text-[#273832]"}`}
          >
            {tab.label}
            <span className="rounded-full bg-[#eef3f1] px-2 py-0.5 text-xs">{counts[tab.value]}</span>
          </Link>
        );
      })}
    </nav>
  );
}
