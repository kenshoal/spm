import { unstable_rethrow } from "next/navigation";
import { requireAnyRole } from "@/lib/auth";
import { buildVenueSearch, type VenueSearchInput } from "@/lib/venue-form";
import { TimeRangeFields } from "../../components/time-range-fields";
import { monthOfDate } from "@/lib/venue-calendar";
import { layoutLabel, ROOM_LAYOUTS, searchVenues } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { VenueResults } from "./venue-results";

const inputClass = "mt-1 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 py-2.5 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function VenueSearchPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireAnyRole(["event_coordinator", "venue_staff", "safety_officer"]);
  const raw = await searchParams;
  const input: VenueSearchInput = {
    required_capacity: first(raw.required_capacity),
    location: first(raw.location),
    date: first(raw.date),
    start_time: first(raw.start_time),
    end_time: first(raw.end_time),
    layout: first(raw.layout),
    facility: first(raw.facility),
    accessibility: first(raw.accessibility),
  };
  const { query, errors } = buildVenueSearch(input);
  const outcome = query === null
    ? null
    : await searchVenues(query).then((venues) => ({ venues, failed: false as const })).catch((error: unknown) => {
        unstable_rethrow(error);
        return { venues: [], failed: true as const };
      });

  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Venue search</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Find a venue</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Only venues that meet every filter are shown. Blocked venues never appear.</p>
      </div>
      <form method="get" noValidate className="mb-8 grid gap-4 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:grid-cols-2 lg:grid-cols-4">
        <label className={labelClass}>Attendees<input name="required_capacity" type="number" min={1} step={1} defaultValue={input.required_capacity} className={inputClass} />{errors.required_capacity ? <span role="alert" className="mt-1 block text-xs font-normal text-[#a23939]">{errors.required_capacity}</span> : null}</label>
        <label className={labelClass}>Location<input name="location" defaultValue={input.location} className={inputClass} /></label>
        <label className={labelClass}>Date<input name="date" type="date" defaultValue={input.date} className={inputClass} />{errors.date ? <span role="alert" className="mt-1 block text-xs font-normal text-[#a23939]">{errors.date}</span> : null}</label>
        <div className="sm:col-span-2">
          <TimeRangeFields start={input.start_time} end={input.end_time} errors={errors} inputClass={inputClass} labelClass={labelClass} optional />
        </div>
        <label className={labelClass}>Layout
          <select name="layout" defaultValue={input.layout} className={inputClass}>
            <option value="">Any layout</option>
            {ROOM_LAYOUTS.map((layout) => <option key={layout} value={layout}>{layoutLabel(layout)}</option>)}
          </select>
        </label>
        <label className={labelClass}>Required facilities<input name="facility" defaultValue={input.facility} placeholder="Projector, WiFi" className={inputClass} /></label>
        <label className={labelClass}>Accessibility needs<input name="accessibility" defaultValue={input.accessibility} placeholder="Ramp access" className={inputClass} /></label>
        <div className="flex items-end"><button type="submit" className="min-h-11 w-full rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d]">Search venues</button></div>
        <p className="text-xs text-[#718078] sm:col-span-2 lg:col-span-4">Venues blocked or booked at an overlapping time on the chosen date are excluded, as are venues blocked as a whole. With only a date, a venue needs some free time that day. A venue free except for a tentative hold is shown as Tentatively held.</p>
      </form>
      {outcome === null ? (
        Object.keys(errors).length ? null : <p className="text-sm text-[#718078]">Add at least one filter to search.</p>
      ) : outcome.failed ? (
        <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The venue service is unavailable. Start the local API on port 8004, then refresh.</div>
      ) : (
        <VenueResults
          venues={outcome.venues}
          month={monthOfDate(input.date ?? "")}
          requirements={{
            expected_attendance: input.required_capacity ?? "",
            required_layout: input.layout ?? "",
            start_time: input.start_time ?? "",
            end_time: input.end_time ?? "",
            required_facilities: input.facility ?? "",
            required_accessibility: input.accessibility ?? "",
          }}
        />
      )}
    </AppShell>
  );
}
