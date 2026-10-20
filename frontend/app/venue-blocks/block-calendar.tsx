import Link from "next/link";
import type { BlockCalendar, CalendarDay } from "@/lib/block-calendar";

function dayLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

// SCRUM-65: one cell per date listing its blocked and booked times.
function Times({ day }: { day: CalendarDay }) {
  if (day.unavailable) {
    return <td className="border-t border-[#eef2f0] bg-[#fbf3ee] px-3 py-2 text-xs font-semibold text-[#8c3a2b]">Unavailable</td>;
  }
  if (day.entries.length === 0) {
    return <td className="border-t border-[#eef2f0] px-3 py-2 text-xs text-[#145c40]">Available all day</td>;
  }
  return (
    <td className="border-t border-[#eef2f0] px-3 py-2 align-top">
      <ul className="space-y-1">
        {day.entries.map((entry, index) => (
          <li key={index} className={`rounded-lg px-2 py-1 text-xs ${entry.state === "blocked" ? "bg-[#fdecea] text-[#793f27]" : "bg-[#e8eefb] text-[#33456b]"}`}>
            <span className="font-bold">{entry.time}</span>{" "}
            <span className="font-bold">{entry.state === "blocked" ? "Blocked" : "Booked"}</span>{" — "}
            <span>{entry.text}</span>
          </li>
        ))}
      </ul>
      <span className="mt-1 block text-xs text-[#145c40]">Other times available</span>
    </td>
  );
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
              <th scope="col" className="px-3 py-2 text-xs font-bold uppercase tracking-[0.1em] text-[#68776f]">Blocked and booked times</th>
            </tr>
          </thead>
          <tbody>
            {calendar.days.map((day) => (
              <tr key={day.date}>
                <th scope="row" className="whitespace-nowrap border-t border-[#eef2f0] px-3 py-2 text-sm font-semibold text-[#273832]">{dayLabel(day.date)}</th>
                <Times day={day} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
