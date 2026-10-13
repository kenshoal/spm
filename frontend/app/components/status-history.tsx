'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { EventStatusHistory } from '@/lib/event-requests';

const PAGE_SIZE = 5;

type StatusHistoryProps = { entries: EventStatusHistory[]; unavailable?: boolean };

export function StatusHistory(props: StatusHistoryProps) {
  // Use the recorded event identity to start a fresh window when the event changes.
  return <StatusHistoryView key={props.entries[0]?.event_request_id ?? 'empty'} {...props} />;
}

function StatusHistoryView({ entries, unavailable = false }: StatusHistoryProps) {
  const router = useRouter();
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  // Copy the authoritative ascending input before reversing its visible window.
  const visibleEntries = entries.slice(-visibleCount).reverse();
  return (
    <section aria-label="Status history" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#17211d]">Status history</h2>
          <p className="mt-1 text-xs text-[#68776f]">Newest first</p>
        </div>
        <button
          type="button"
          onClick={() => router.refresh()}
          className="min-h-11 rounded-lg border border-[#cfd9d4] bg-white px-4 py-2.5 text-sm font-semibold text-[#0f6b5b] hover:bg-[#f4f7f5] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b]"
        >
          Refresh status and history
        </button>
      </div>
      {unavailable ? (
        <p role="alert" className="mt-3 text-sm text-[#793f27]">Status history is temporarily unavailable. Refresh to try again.</p>
      ) : entries.length === 0 ? (
        <p className="mt-3 text-sm text-[#68776f]">No status history is available yet.</p>
      ) : (
        <ol aria-label="Event status activity" className="mt-4 space-y-5 border-l-2 border-[#dce4e0] pl-5">
          {visibleEntries.map((entry) => (
            <li key={entry.id} className="relative">
              <span aria-hidden="true" className="absolute -left-[1.7rem] top-1.5 size-3 rounded-full border-2 border-white bg-[#0f6b5b]" />
              <p className="font-semibold text-[#253b32]">
                {entry.entry_kind === 'baseline' ? `History recording started · ${entry.new_status}`
                  : entry.entry_kind === 'created' ? `Created as ${entry.new_status}`
                    : `${entry.previous_status} → ${entry.new_status}`}
              </p>
              <p className="mt-1 break-words text-sm text-[#526159]">
                {entry.actor_role === 'system' ? 'System'
                  : entry.actor_role === 'event_organiser' ? 'Event Organiser'
                    : entry.actor_role === 'event_coordinator' ? 'Event Coordinator'
                      : entry.actor_role.replaceAll('_', ' ')}
                {entry.actor_id ? ` · ${entry.actor_id}` : null}
              </p>
              <time dateTime={entry.occurred_at} className="mt-1 block text-xs text-[#68776f]">
                {new Intl.DateTimeFormat('en-SG', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Singapore' }).format(new Date(entry.occurred_at))}
              </time>
              {entry.entry_kind === 'baseline' ? <p className="mt-1 text-xs text-[#68776f]">Earlier transitions were not recorded.</p> : null}
            </li>
          ))}
        </ol>
      )}
      {!unavailable && entries.length > visibleCount ? (
        <button
          type="button"
          onClick={() => setVisibleCount((count) => Math.min(count + PAGE_SIZE, entries.length))}
          className="mt-5 min-h-11 rounded-lg border border-[#cfd9d4] bg-white px-4 py-2.5 text-sm font-semibold text-[#0f6b5b] hover:bg-[#f4f7f5] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f6b5b]"
        >
          Show older activity
        </button>
      ) : null}
    </section>
  );
}

export function StatusHistoryLoading() {
  return <p role="status" className="mt-5 p-6 text-sm text-[#68776f]">Loading status history…</p>;
}
