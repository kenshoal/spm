import { END_TIMES, START_TIMES, timeLabel } from "@/lib/venue-options";

// SCRUM-65: start and end time pickers in 15-minute steps within 07:00-24:00.
// Plain selects, so they work in server and client components alike.
export function TimeRangeFields({
  start,
  end,
  errors = {},
  inputClass,
  labelClass,
  optional = false,
}: {
  start?: string;
  end?: string;
  errors?: Record<string, string | undefined>;
  inputClass: string;
  labelClass: string;
  optional?: boolean;
}) {
  const blank = optional ? "Any" : "Choose";
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className={labelClass}>Start time
        <select name="start_time" defaultValue={start ?? ""} className={inputClass}>
          <option value="">{blank}</option>
          {START_TIMES.map((m) => <option key={m} value={timeLabel(m)}>{timeLabel(m)}</option>)}
        </select>
        {errors.start_time ? <p className="mt-1 text-sm text-[#a23939]">{errors.start_time}</p> : null}
      </label>
      <label className={labelClass}>End time
        <select name="end_time" defaultValue={end ?? ""} className={inputClass}>
          <option value="">{blank}</option>
          {END_TIMES.map((m) => <option key={m} value={timeLabel(m)}>{timeLabel(m)}</option>)}
        </select>
        {errors.end_time ? <p className="mt-1 text-sm text-[#a23939]">{errors.end_time}</p> : null}
      </label>
    </div>
  );
}
