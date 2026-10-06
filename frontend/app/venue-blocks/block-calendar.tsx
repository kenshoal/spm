import Link from "next/link";
import type { BlockCalendar, CalendarCell } from "@/lib/block-calendar";
import { SLOTS } from "@/lib/venue-options";

function dayLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

function Cell({ cell }: { cell: CalendarCell }) {
  if (cell.state === "blocked") {
    return (
      <td className="border-t border-[#eef2f0] bg-[#fdecea] px-3 py-2 align-top">
        <span className="block text-xs font-bold text-[#8c3a2b]">Blocked</span>
        {cell.reasons.map((reason, index) => <span key={index} className="block text-xs text-[#793f27]">{reason}</span>)}
      </td>
    );
  }
  if (cell.state === "unavailable") {
    return <td className="border-t border-[#eef2f0] bg-[#fbf3ee] px-3 py-2 text-xs font-semibold text-[#8c3a2b]">Unavailable</td>;
  }
  if (cell.state === "not_offered") {
    return <td className="border-t border-[#eef2f0] bg-[#f4f6f5] px-3 py-2 text-xs text-[#8a958f]">Not offered</td>;
  }
  return <td className="border-t border-[#eef2f0] px-3 py-2 text-xs text-[#145c40]">Available</td>;
}

export function BlockCalendarTable({ calendar, venueId, venueName }: { calendar: BlockCalendar; venueId: string; venueName: string }) {
  const href = (month: string) => `/venue-blocks?venue=${encodeURIComponent(venueId)}&month=${month}`;
  return (
    <section className="rounded-2xl border border-[#dce4e0] bg-white p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold text-[#1b2b25]">{calendar.label}</h2>
        <div className="flex gap-4 text-sm font-semibold">
          <Link href={href(calendar.previousMonth)} className="text-[#0f6b5b] hover:underline">Previous month</Link>
          <Link href={href(calendar.nextMonth)} className="text-[#0f6b5b] hover:underline">Next month</Link>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] border-collapse text-left">
          <caption className="sr-only">{`${venueName} availability, ${calendar.label}`}</caption>
          <thead>
            <tr>
              <th scope="col" className="px-3 py-2 text-xs font-bold uppercase tracking-[0.1em] text-[#68776f]">Date</th>
              {SLOTS.map((slot) => <th key={slot} scope="col" className="px-3 py-2 text-xs font-bold uppercase tracking-[0.1em] text-[#68776f]">{slot}</th>)}
            </tr>
          </thead>
          <tbody>
            {calendar.days.map((day) => (
              <tr key={day.date}>
                <th scope="row" className="whitespace-nowrap border-t border-[#eef2f0] px-3 py-2 text-sm font-semibold text-[#273832]">{dayLabel(day.date)}</th>
                {day.cells.map((cell) => <Cell key={cell.slot} cell={cell} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
