import type { SuitabilityFormValues } from "@/lib/venue-suitability";
import { layoutLabel, prepTimeLabel, type Venue } from "@/lib/venues";
import { SuitabilityCheck } from "./suitability-check";

const NO_REQUIREMENTS: SuitabilityFormValues = {
  expected_attendance: "", required_layout: "", required_slot: "", required_facilities: "", required_accessibility: "",
};

export function VenueResults({ venues, requirements = NO_REQUIREMENTS }: { venues: Venue[]; requirements?: SuitabilityFormValues }) {
  if (venues.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-10 text-center text-sm text-[#718078]">No venue matches every filter. Try removing one.</p>;
  }
  return (
    <div>
      <p role="status" className="mb-3 text-sm font-semibold text-[#34463f]">{venues.length} {venues.length === 1 ? "venue matches" : "venues match"} every filter.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {venues.map((venue) => (
          <article key={venue.id} aria-labelledby={`result-${venue.id}`} className="rounded-2xl border border-[#dce4e0] bg-white p-5">
            <h3 id={`result-${venue.id}`} className="text-lg font-bold text-[#1b2b25]">{venue.name}</h3>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-[#718078]">Location</dt><dd className="text-[#273832]">{venue.location}</dd>
              <dt className="text-[#718078]">Capacity</dt><dd className="text-[#273832]">{venue.max_capacity} people</dd>
              <dt className="text-[#718078]">Layouts</dt><dd className="text-[#273832]">{venue.supported_layouts.map(layoutLabel).join(", ") || "None recorded"}</dd>
              <dt className="text-[#718078]">Facilities</dt><dd className="text-[#273832]">{venue.facilities.join(", ") || "None recorded"}</dd>
              <dt className="text-[#718078]">Accessibility</dt><dd className="text-[#273832]">{venue.accessibility_features.join(", ") || "None recorded"}</dd>
              <dt className="text-[#718078]">Slots</dt><dd className="text-[#273832]">{venue.operating_slots.join(", ")}</dd>
              <dt className="text-[#718078]">Setup</dt><dd className="text-[#273832]">{prepTimeLabel(venue.setup_minutes)}</dd>
              <dt className="text-[#718078]">Turnaround</dt><dd className="text-[#273832]">{prepTimeLabel(venue.turnaround_minutes)}</dd>
            </dl>
            <SuitabilityCheck venueId={venue.id} defaults={requirements} />
          </article>
        ))}
      </div>
    </div>
  );
}
