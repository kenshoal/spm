"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import {
  createEventRequest,
  type EventRequestFormState,
  updateEventRequest,
} from "../actions";
import type { EventRequest } from "@/lib/event-requests";

const initialState: EventRequestFormState = {};

function FieldError({ error }: { error?: string }) {
  return error ? <p className="mt-1.5 text-sm text-[#a33a35]">{error}</p> : null;
}

const inputClass =
  "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832] outline-none transition placeholder:text-[#9aa49f] focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]";

function toDateTimeLocal(value: string): string {
  const date = new Date(value);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Singapore",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function EventRequestForm({ request }: { request?: EventRequest }) {
  const action = request
    ? updateEventRequest.bind(null, request.id)
    : createEventRequest;
  const [state, formAction, pending] = useActionState(
    action,
    initialState,
  );
  const initialDates = request?.proposed_date_times.length
    ? request.proposed_date_times.map((value, id) => ({ id, value }))
    : [{ id: 0, value: "" }];
  const [dateOptions, setDateOptions] = useState(initialDates);

  return (
    <form action={formAction} className="space-y-6">
      {state.message && (
        <div role="alert" className="rounded-xl border border-[#efc7c4] bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">
          {state.message}
        </div>
      )}

      <section className="rounded-2xl border border-[#dce4e0] bg-white p-6 shadow-[0_1px_2px_rgba(22,46,37,0.04)] sm:p-7">
        <h2 className="text-lg font-bold text-[#17211d]">Event information</h2>
        <p className="mt-1 text-sm text-[#718078]">Tell the coordination team what you are organising.</p>
        <div className="mt-6 space-y-5">
          <label className="block text-sm font-semibold text-[#34463f]">
            Event name
            <input name="event_name" defaultValue={request?.event_name ?? ""} maxLength={200} className={inputClass} placeholder="e.g. Community technology workshop" />
            <FieldError error={state.errors?.event_name} />
          </label>
          <label className="block text-sm font-semibold text-[#34463f]">
            Purpose
            <textarea name="purpose" defaultValue={request?.purpose ?? ""} maxLength={1000} rows={3} className={inputClass} placeholder="What should this event achieve?" />
            <FieldError error={state.errors?.purpose} />
          </label>
          <label className="block text-sm font-semibold text-[#34463f]">
            Description
            <textarea name="description" defaultValue={request?.description ?? ""} maxLength={5000} rows={5} className={inputClass} placeholder="Describe the programme, audience, and activities." />
            <FieldError error={state.errors?.description} />
          </label>
        </div>
      </section>

      <section className="rounded-2xl border border-[#dce4e0] bg-white p-6 shadow-[0_1px_2px_rgba(22,46,37,0.04)] sm:p-7">
        <h2 className="text-lg font-bold text-[#17211d]">Schedule and attendance</h2>
        <p className="mt-1 text-sm text-[#718078]">Add one or more possible dates for coordination.</p>
        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          <div>
            <span className="text-sm font-semibold text-[#34463f]">Proposed date and time</span>
            <div className="space-y-3">
              {dateOptions.map((option, index) => (
                <div key={option.id} className="flex items-center gap-2">
                  <input type="datetime-local" name="proposed_date_times" defaultValue={option.value ? toDateTimeLocal(option.value) : ""} className={inputClass} aria-label={`Proposed date and time ${index + 1}`} />
                  {index > 0 && <button type="button" onClick={() => setDateOptions((items) => items.filter((item) => item.id !== option.id))} className="mt-2 rounded-lg px-3 py-3 text-sm font-semibold text-[#8e3d35] hover:bg-[#fff0ef]">Remove</button>}
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setDateOptions((items) => [...items, { id: Math.max(...items.map((item) => item.id)) + 1, value: "" }])} className="mt-3 text-sm font-semibold text-[#0f6b5b] hover:underline">+ Add another option</button>
            <FieldError error={state.errors?.proposed_date_times} />
          </div>
          <label className="block text-sm font-semibold text-[#34463f]">
            Expected attendance
            <input type="number" name="expected_attendance" defaultValue={request?.expected_attendance ?? ""} min={1} step={1} className={inputClass} placeholder="e.g. 40" />
            <FieldError error={state.errors?.expected_attendance} />
          </label>
        </div>
      </section>

      <section className="rounded-2xl border border-[#dce4e0] bg-white p-6 shadow-[0_1px_2px_rgba(22,46,37,0.04)] sm:p-7">
        <h2 className="text-lg font-bold text-[#17211d]">Event requirements</h2>
        <p className="mt-1 text-sm text-[#718078]">Enter “No special requirements” where a category does not apply.</p>
        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          {[
            ["venue_requirements", "Venue requirements", "Room type, location, layout, or capacity"],
            ["equipment_requirements", "Equipment requirements", "AV, microphones, laptops, staging, or power"],
            ["accessibility_needs", "Accessibility needs", "Mobility, hearing, visual, or dietary support"],
            ["registration_needs", "Registration needs", "Ticketing, check-in, capacity, or attendee information"],
          ].map(([name, label, placeholder]) => (
            <label key={name} className="block text-sm font-semibold text-[#34463f]">
              {label}
              <textarea name={name} defaultValue={request?.[name as keyof EventRequest] as string | null ?? ""} maxLength={2000} rows={4} className={inputClass} placeholder={placeholder} />
              <FieldError error={state.errors?.[name]} />
            </label>
          ))}
        </div>
      </section>

      <div className="sticky bottom-4 flex flex-col-reverse gap-3 rounded-2xl border border-[#dce4e0] bg-white/95 p-4 shadow-[0_10px_35px_rgba(22,46,37,0.14)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <Link href="/event-requests" className="inline-flex min-h-11 items-center justify-center rounded-xl px-5 text-sm font-semibold text-[#526159] hover:bg-[#f1f5f3]">Cancel</Link>
        <button type="submit" formNoValidate disabled={pending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white shadow-sm hover:bg-[#0b5b4d] disabled:opacity-50">{pending ? "Saving…" : request ? "Save changes" : "Save draft"}</button>
      </div>
    </form>
  );
}
