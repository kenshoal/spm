"use client";

import { useActionState, useState } from "react";
import type { EventChangeRequest } from "@/lib/event-requests";
import { decideEventChangeRequest, type ChangeDecision } from "../../actions";

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
  }).format(new Date(value));
}

const labels: Record<string, string> = {
  proposed_date_times: "Proposed date and time",
  expected_attendance: "Expected attendance",
  venue_requirements: "Venue requirements",
  equipment_requirements: "Equipment requirements",
  registration_needs: "Registration needs",
};

function valueText(key: string, value: unknown): string {
  if (key === "proposed_date_times" && Array.isArray(value)) {
    return value.map((item) => formatDateTime(String(item))).join(", ");
  }
  return String(value);
}

function DecisionDialog({ eventRequestId, request, decision, close }: {
  eventRequestId: string;
  request: EventChangeRequest;
  decision: ChangeDecision;
  close: () => void;
}) {
  const action = decideEventChangeRequest.bind(null, eventRequestId, request.id, decision);
  const [state, formAction, pending] = useActionState(action, {});
  const rejecting = decision === "Rejected";
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[#15241f]/45 p-4">
      <section role="dialog" aria-modal="true" aria-labelledby="change-decision-title" className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
        <h3 id="change-decision-title" className="text-xl font-bold text-[#1b2b25]">{rejecting ? "Reject this change?" : "Approve this change?"}</h3>
        <p className="mt-2 text-sm text-[#68776f]">{rejecting ? "The current event plan will remain unchanged." : "All proposed values will replace their matching values in the event plan."}</p>
        <form action={formAction} className="mt-5">
          <label className="block text-sm font-semibold text-[#34463f]">Decision reason
            <textarea name="reason" required={rejecting} maxLength={2000} rows={4} className="mt-2 w-full rounded-xl border border-[#cfd9d4] px-4 py-3" />
          </label>
          {state.message ? <p role="alert" className="mt-3 text-sm text-[#a23939]">{state.message}</p> : null}
          <div className="mt-5 flex justify-end gap-3">
            <button type="button" onClick={close} className="rounded-lg border border-[#ccd8d2] px-4 py-2.5 text-sm font-semibold">Cancel</button>
            <button disabled={pending} className="rounded-lg bg-[#0f6b5b] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">{rejecting ? "Reject change" : "Approve change"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

export function ChangeRequestPanel({ eventRequestId, requests }: { eventRequestId: string; requests: EventChangeRequest[] }) {
  const [selected, setSelected] = useState<{ request: EventChangeRequest; decision: ChangeDecision } | null>(null);
  if (requests.length === 0) return null;
  return (
    <section aria-labelledby="change-requests-title" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 id="change-requests-title" className="text-lg font-bold text-[#17211d]">Event change requests</h2>
      <div className="mt-4 space-y-4">
        {requests.map((request) => (
          <article key={request.id} className="rounded-xl border border-[#dce4e0] p-4">
            <div className="flex items-center justify-between gap-3"><strong>{request.status}</strong><span className="text-xs text-[#718078]">{formatDateTime(request.created_at)}</span></div>
            <p className="mt-2 text-sm text-[#526159]">{request.explanation}</p>
            <dl className="mt-3 grid gap-2 text-sm">
              {Object.entries(request.proposed_changes).map(([key, value]) => (
                <div key={key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-3"><dt className="font-semibold text-[#526159]">{labels[key] ?? key}</dt><dd>{valueText(key, value)}</dd></div>
              ))}
            </dl>
            {request.decision_reason ? <p className="mt-3 text-sm"><strong>Decision reason:</strong> {request.decision_reason}</p> : null}
            {request.status === "Pending" ? (
              <div className="mt-4 flex gap-3"><button onClick={() => setSelected({ request, decision: "Approved" })} className="rounded-lg bg-[#0f6b5b] px-4 py-2 text-sm font-semibold text-white">Approve change</button><button onClick={() => setSelected({ request, decision: "Rejected" })} className="rounded-lg border border-[#c86a5a] px-4 py-2 text-sm font-semibold text-[#8c3a2b]">Reject change</button></div>
            ) : null}
          </article>
        ))}
      </div>
      {selected ? <DecisionDialog eventRequestId={eventRequestId} request={selected.request} decision={selected.decision} close={() => setSelected(null)} /> : null}
    </section>
  );
}
