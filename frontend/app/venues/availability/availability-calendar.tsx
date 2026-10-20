import Link from "next/link";
import { adjacentMonths, monthLabel, STATE_LABELS, type CalendarState, type VenueCalendar } from "@/lib/venue-calendar";
import { SLOTS } from "@/lib/venue-options";

const STATE_STYLES: Record<CalendarState, string> = {
  open: "text-[#145c40]",
  booked: "bg-[#e8eefb] font-semibold text-[#2b4a8c]",
  blocked: "bg-[#fdecea] font-semibold text-[#8c3a2b]",
  unavailable: "bg-[#fbf3ee] font-semibold text-[#8c3a2b]",
  not_offered: "bg-[#f4f6f5] text-[#8a958f]",
};

function dayLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

// Read-only: a venue's slots for one month, each state written out. It shows
// no reasons or event names; Venue Staff see those on the venue blocks page.
export function AvailabilityCalendarTable({ calendar, venueId, venueName }: { calendar: VenueCalendar; venueId: string; venueName: string }) {
  const label = monthLabel(calendar.month);
  const { previous, next } = adjacentMonths(calendar.month);
  const href = (month: string) => `/venues/availability?venue=${encodeURIComponent(venueId)}&month=${month}`;
  return (
    <section className="rounded-2xl border border-[#dce4e0] bg-white p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold text-[#1b2b25]">{label}</h2>
        <div className="flex gap-4 text-sm font-semibold">
          <Link href={href(previous)} className="text-[#0f6b5b] hover:underline">Previous month</Link>
          <Link href={href(next)} className="text-[#0f6b5b] hover:underline">Next month</Link>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] border-collapse text-left">
          <caption className="sr-only">{`${venueName} availability, ${label}`}</caption>
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
                {day.slots.map((cell) => (
                  <td key={cell.slot} className={`border-t border-[#eef2f0] px-3 py-2 text-xs ${STATE_STYLES[cell.state]}`}>{STATE_LABELS[cell.state]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
