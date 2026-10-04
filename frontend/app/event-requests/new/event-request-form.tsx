"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import {
  createEventRequest,
  type EventRequestFormState,
  submitDraftEventRequest,
  submitNewEventRequest,
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
  const draftAction = request
    ? updateEventRequest.bind(null, request.id)
    : createEventRequest;
  const submissionAction = request
    ? submitDraftEventRequest.bind(null, request.id)
    : submitNewEventRequest;
  const [draftState, draftFormAction, draftPending] = useActionState(
    draftAction,
    initialState,
  );
  const [submissionState, submissionFormAction, submissionPending] =
    useActionState(submissionAction, initialState);
  const [isConfirmingSubmission, setIsConfirmingSubmission] = useState(false);
  const state = submissionState.message || submissionState.errors
    ? submissionState
    : draftState;
  const pending = draftPending || submissionPending;
  const initialDates = request?.proposed_date_times.length
    ? request.proposed_date_times.map((value, id) => ({ id, value }))
    : [{ id: 0, value: "" }];
  const [dateOptions, setDateOptions] = useState(initialDates);

  return (
    <form
      action={draftFormAction}
      className="space-y-6"
    >
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
            <input name="event_name" defaultValue={request?.event_name ?? ""} required maxLength={200} className={inputClass} placeholder="e.g. Community technology workshop" />
            <FieldError error={state.errors?.event_name} />
          </label>
          <label className="block text-sm font-semibold text-[#34463f]">
            Purpose
            <textarea name="purpose" defaultValue={request?.purpose ?? ""} required maxLength={1000} rows={3} className={inputClass} placeholder="What should this event achieve?" />
            <FieldError error={state.errors?.purpose} />
          </label>
          <label className="block text-sm font-semibold text-[#34463f]">
            Description
            <textarea name="description" defaultValue={request?.description ?? ""} required maxLength={5000} rows={5} className={inputClass} placeholder="Describe the programme, audience, and activities." />
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
                  <input type="datetime-local" name="proposed_date_times" defaultValue={option.value ? toDateTimeLocal(option.value) : ""} required={index === 0} className={inputClass} aria-label={`Proposed date and time ${index + 1}`} />
                  {index > 0 && <button type="button" onClick={() => setDateOptions((items) => items.filter((item) => item.id !== option.id))} className="mt-2 rounded-lg px-3 py-3 text-sm font-semibold text-[#8e3d35] hover:bg-[#fff0ef]">Remove</button>}
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setDateOptions((items) => [...items, { id: Math.max(...items.map((item) => item.id)) + 1, value: "" }])} className="mt-3 text-sm font-semibold text-[#0f6b5b] hover:underline">+ Add another option</button>
            <FieldError error={state.errors?.proposed_date_times} />
          </div>
          <label className="block text-sm font-semibold text-[#34463f]">
            Expected attendance
            <input type="number" name="expected_attendance" defaultValue={request?.expected_attendance ?? ""} required min={1} step={1} className={inputClass} placeholder="e.g. 40" />
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
              <textarea name={name} defaultValue={request?.[name as keyof EventRequest] as string | null ?? ""} required maxLength={2000} rows={4} className={inputClass} placeholder={placeholder} />
              <FieldError error={state.errors?.[name]} />
            </label>
          ))}
        </div>
      </section>

      <div className="sticky bottom-4 flex flex-col-reverse gap-3 rounded-2xl border border-[#dce4e0] bg-white/95 p-4 shadow-[0_10px_35px_rgba(22,46,37,0.14)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <Link href="/event-requests" className="inline-flex min-h-11 items-center justify-center rounded-xl px-5 text-sm font-semibold text-[#526159] hover:bg-[#f1f5f3]">Cancel</Link>
        <div className="flex flex-col gap-3 sm:flex-row">
          <button type="submit" formNoValidate disabled={pending} className="min-h-11 rounded-xl border border-[#0f6b5b] px-5 text-sm font-bold text-[#0f6b5b] hover:bg-[#edf7f3] disabled:opacity-50">{draftPending ? "Saving…" : request ? "Save changes" : "Save draft"}</button>
          <button
            type="button"
            disabled={pending}
            onClick={(event) => {
              const form = event.currentTarget.form;
              if (form?.reportValidity()) setIsConfirmingSubmission(true);
            }}
            className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white shadow-sm hover:bg-[#0b5b4d] disabled:opacity-50"
          >
            Submit request
          </button>
        </div>
      </div>

      {isConfirmingSubmission ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-[#15241f]/45 p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !submissionPending) {
              setIsConfirmingSubmission(false);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape" && !submissionPending) {
              setIsConfirmingSubmission(false);
            }
          }}
        >
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="submit-event-request-title"
            aria-describedby="submit-event-request-description"
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-[0_24px_80px_rgba(18,39,32,0.28)]"
          >
            <h2 id="submit-event-request-title" className="text-xl font-bold text-[#1b2b25]">Submit event request?</h2>
            <p id="submit-event-request-description" className="mt-2 text-sm leading-6 text-[#68776f]">
              The coordination team will receive this request. You cannot edit or delete it after submission.
            </p>
            {submissionState.message ? (
              <p role="alert" className="mt-4 rounded-lg border border-[#efc7c4] bg-[#fff4f3] px-3 py-2 text-sm text-[#8e3d35]">
                {submissionState.message}
              </p>
            ) : null}
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" autoFocus disabled={submissionPending} onClick={() => setIsConfirmingSubmission(false)} className="rounded-lg border border-[#ccd8d2] px-4 py-2.5 text-sm font-semibold text-[#34473f] hover:bg-[#f4f7f5] disabled:opacity-60">Cancel</button>
              <button type="submit" formAction={submissionFormAction} disabled={submissionPending} className="rounded-lg bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
                {submissionPending ? "Submitting…" : "Submit request"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </form>
  );
}
