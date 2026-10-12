import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { StatusHistory, StatusHistoryLoading } from '@/app/components/status-history';
import type { EventStatusHistory } from '@/lib/event-requests';

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => navigation }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const created: EventStatusHistory = {
  id: 1, event_request_id: 'event-1', previous_status: null, new_status: 'Submitted',
  actor_id: 'organiser-1', actor_role: 'event_organiser', source: 'event_request.created',
  entry_kind: 'created', occurred_at: '2026-10-10T01:00:00Z',
};
const reviewed: EventStatusHistory = {
  ...created, id: 2, previous_status: 'Submitted', new_status: 'Under Review',
  actor_id: 'coordinator-1', actor_role: 'event_coordinator', source: 'coordinator.review',
  entry_kind: 'transition', occurred_at: '2026-10-10T02:00:00Z',
};

// AC7-H1 (happy): the approved newest-first timeline retains actual actors and semantic times
test('AC7-H1 shows newest-first activity with actor and semantic timestamps', () => {
  render(<StatusHistory entries={[created, reviewed]} />);
  const items = within(screen.getByRole('list', { name: 'Event status activity' })).getAllByRole('listitem');
  expect(items).toHaveLength(2);
  expect(screen.getByText('Newest first')).toBeDefined();
  expect(items[1].textContent).toContain('Created as Submitted');
  expect(items[0].textContent).toContain('Submitted → Under Review');
  expect(items[0].textContent).toContain('Event Coordinator');
  expect(items[0].textContent).toContain('coordinator-1');
  expect(items[0].querySelector('time')?.getAttribute('dateTime')).toBe(reviewed.occurred_at);
});

// AC4-B1 (boundary): zero recorded entries must not invent a creation or a transition
test('shows an explicit empty history', () => {
  render(<StatusHistory entries={[]} />);
  expect(screen.getByText('No status history is available yet.')).toBeDefined();
  expect(screen.queryAllByRole('listitem')).toHaveLength(0);
});

// AC4-B2 (boundary): a single creation entry remains a readable timeline
test('shows a single creation entry', () => {
  render(<StatusHistory entries={[created]} />);
  expect(screen.getAllByRole('listitem')).toHaveLength(1);
  expect(screen.getByText('Created as Submitted')).toBeDefined();
});

// AC4-X1 (cross-cutting): legacy baselines must not impersonate historical creation evidence
test('labels a legacy baseline without an invented user', () => {
  render(<StatusHistory entries={[{ ...created, actor_id: null, actor_role: 'system',
    entry_kind: 'baseline', source: 'history.recording_started' }]} />);
  expect(screen.getByText('History recording started · Submitted')).toBeDefined();
  expect(screen.getByText('Earlier transitions were not recorded.')).toBeDefined();
  expect(screen.getByText('System')).toBeDefined();
  expect(screen.queryByText('organiser-1')).toBeNull();
});

// AC7-N1 (negative): a failed lookup must be an accessible error, not an empty-history success
test('shows an accessible unavailable message', () => {
  render(<StatusHistory entries={[]} unavailable />);
  expect(screen.getByRole('alert').textContent).toContain('Status history is temporarily unavailable');
  expect(screen.queryByText('No status history is available yet.')).toBeNull();
});

// AC7-B1 (boundary): the pending lookup communicates progress to assistive technology
test('announces history loading', () => {
  render(<StatusHistoryLoading />);
  expect(screen.getByRole('status').textContent).toBe('Loading status history…');
  expect(screen.queryByRole('alert')).toBeNull();
});


function ascendingHistory(count: number): EventStatusHistory[] {
  return Array.from({ length: count }, (_, index) => {
    const id = index + 1;
    const newStatus = id === 1 ? 'Submitted' : id % 2 === 0 ? 'Under Review' : 'Changes Requested';
    return {
      ...created, id, actor_id: `actor-${id}`, new_status: newStatus,
      previous_status: id === 1 ? null : id === 2 ? 'Submitted' : id % 2 === 0 ? 'Changes Requested' : 'Under Review',
      actor_role: id === 1 ? 'event_organiser' : 'event_coordinator',
      entry_kind: id === 1 ? 'created' : 'transition',
      source: id === 1 ? 'event_request.created' : id === 2 ? 'coordinator.review' : id % 2 === 0 ? 'coordinator.resume_review' : 'coordinator.decision',
      occurred_at: `2026-10-12T01:${String(index).padStart(2, '0')}:00Z`,
    };
  });
}
function visibleActors() {
  return screen.getAllByRole('listitem').map(item => item.querySelectorAll('p')[1]?.textContent?.match(/actor-\d+/)?.[0]);
}

// AC7-B2 (boundary): four entries fit without an older-activity control.
// AC7-B3 (boundary): exactly five entries fit without an older-activity control.
// AC7-B4 (boundary): the sixth entry is hidden until the first reveal and then exhausts history.
test.each([
  { id: 'AC7-B2', count: 4, expected: [4, 3, 2, 1] },
  { id: 'AC7-B3', count: 5, expected: [5, 4, 3, 2, 1] },
  { id: 'AC7-B4', count: 6, expected: [6, 5, 4, 3, 2] },
])('$id initially shows at most five of $count entries', ({ count, expected }) => {
  render(<StatusHistory entries={ascendingHistory(count)} />);
  expect(visibleActors()).toEqual(expected.map(id => `actor-${id}`));
  const older = screen.queryByRole('button', { name: 'Show older activity' });
  if (count === 6) {
    expect(older).not.toBeNull();
    fireEvent.click(older!);
    expect(visibleActors()).toEqual([6, 5, 4, 3, 2, 1].map(id => `actor-${id}`));
    expect(screen.queryByRole('button', { name: 'Show older activity' })).toBeNull();
  } else {
    expect(older).toBeNull();
  }
  expect(navigation.refresh).not.toHaveBeenCalled();
});

// AC7-H2 (happy): successive five-entry reveals retain every entry and leave ascending API data untouched.
test('AC7-H2 reveals twelve entries in two further batches without mutating input', () => {
  const entries = ascendingHistory(12);
  const before = structuredClone(entries);
  entries.forEach(Object.freeze);
  Object.freeze(entries);
  render(<StatusHistory entries={entries} />);
  expect(visibleActors()).toEqual([12, 11, 10, 9, 8].map(id => `actor-${id}`));
  fireEvent.click(screen.getByRole('button', { name: 'Show older activity' }));
  expect(visibleActors()).toEqual([12, 11, 10, 9, 8, 7, 6, 5, 4, 3].map(id => `actor-${id}`));
  fireEvent.click(screen.getByRole('button', { name: 'Show older activity' }));
  expect(visibleActors()).toEqual([12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map(id => `actor-${id}`));
  expect(screen.queryByRole('button', { name: 'Show older activity' })).toBeNull();
  expect(entries).toEqual(before);
  expect(navigation.refresh).not.toHaveBeenCalled();
});

// AC4-X9 (cross-cutting): reversing the authoritative ascending order preserves its timestamp tie-break.
test('AC4-X9 shows the higher history ID first for an equal latest timestamp', () => {
  const entries = ascendingHistory(6);
  entries[5].occurred_at = entries[4].occurred_at;
  const before = structuredClone(entries);
  render(<StatusHistory entries={entries} />);
  expect(visibleActors()).toEqual([6, 5, 4, 3, 2].map(id => `actor-${id}`));
  expect(entries).toEqual(before);
});

// AC7-P1 (partition): populated history offers an explicit whole-view refresh without refreshing on render.
// AC7-P2 (partition): empty history can retry the whole view without inventing an entry.
// AC7-P3 (partition): unavailable history can retry while retaining its accessible error state.
test.each([
  { id: 'AC7-P1', entries: [created, reviewed], unavailable: false },
  { id: 'AC7-P2', entries: [], unavailable: false },
  { id: 'AC7-P3', entries: [], unavailable: true },
])('$id refreshes status and history only on explicit activation', ({ entries, unavailable }) => {
  const before = structuredClone(entries);
  render(<StatusHistory entries={entries} unavailable={unavailable} />);
  expect(navigation.refresh).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Refresh status and history' }));
  expect(navigation.refresh).toHaveBeenCalledTimes(1);
  expect(entries).toEqual(before);
  if (unavailable) expect(screen.getByRole('alert')).toBeDefined();
  else if (entries.length === 0) expect(screen.getByText('No status history is available yet.')).toBeDefined();
});
