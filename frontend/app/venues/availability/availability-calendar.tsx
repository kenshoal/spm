import Link from "next/link";
import { adjacentMonths, ENTRY_LABELS, monthLabel, type CalendarDay, type VenueCalendar } from "@/lib/venue-calendar";
import { CLOSE_MINUTE, OPEN_MINUTE, timeRangeLabel } from "@/lib/venue-options";

const ENTRY_STYLES = {
  booked: "bg-[#e8eefb] text-[#33456b]",
  blocked: "bg-[#fdecea] text-[#793f27]",
  held: "bg-[#fff6dd] text-[#6f4b12]",
} as const;

function dayLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

// The free time of one date, written out: "Available all day", a list of ranges
// or "No free time".
function freeText(day: CalendarDay): { text: string; free: boolean } {
  if (day.free.length === 0) return { text: "No free time", free: false };
  const [only] = day.free;
  if (day.free.length === 1 && only.start_minute === OPEN_MINUTE && only.end_minute === CLOSE_MINUTE) {
    return { text: "Available all day", free: true };
  }
  return { text: `Available ${day.free.map((range) => timeRangeLabel(range.start_minute, range.end_minute)).join(", ")}`, free: true };
}

function Times({ day }: { day: CalendarDay }) {
  if (day.unavailable) {
    return <td className="border-t border-[#eef2f0] bg-[#fbf3ee] px-3 py-2 text-xs font-semibold text-[#8c3a2b]">Unavailable</td>;
  }
  const { text, free } = freeText(day);
  return (
    <td className="border-t border-[#eef2f0] px-3 py-2 align-top">
      {day.entries.length > 0 ? (
        <ul className="mb-1 space-y-1">
          {day.entries.map((entry, index) => (
            <li key={index} className={`rounded-lg px-2 py-1 text-xs font-semibold ${ENTRY_STYLES[entry.state]}`}>
              {ENTRY_LABELS[entry.state]} {timeRangeLabel(entry.start_minute, entry.end_minute)}
            </li>
          ))}
        </ul>
      ) : null}
      <p className={`text-xs ${free ? "text-[#145c40]" : "font-semibold text-[#8c3a2b]"}`}>{text}</p>
    </td>
  );
}

// Read-only: a venue's booked, blocked and free times for one month, each in
// words. It shows no reasons or event names; Venue Staff see those on the venue
// blocks page.
export function AvailabilityCalendarTable({ calendar, venueId, venueName }: { calendar: VenueCalendar; venueId: string; venueName: string }) {
  const label = monthLabel(calendar.month);
  const { previous, next } = adjacentMonths(calendar.month);
  const href = (month: string) => `/venues/availability?venue=${encodeURIComponent(venueId)}&month=${month}`;
  return (
    <section className="rounded-2xl border border-[#dce4e0] bg-white p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold text-[#1b2b25]">{label}</h2>
        <div className="flex gap-4 text-sm font-semibold">
          {previous ? <Link href={href(previous)} className="text-[#0f6b5b] hover:underline">Previous month</Link> : null}
          {next ? <Link href={href(next)} className="text-[#0f6b5b] hover:underline">Next month</Link> : null}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] border-collapse text-left">
          <caption className="sr-only">{`${venueName} availability, ${label}`}</caption>
          <thead>
            <tr>
              <th scope="col" className="px-3 py-2 text-xs font-bold uppercase tracking-[0.1em] text-[#68776f]">Date</th>
              <th scope="col" className="px-3 py-2 text-xs font-bold uppercase tracking-[0.1em] text-[#68776f]">Times</th>
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
