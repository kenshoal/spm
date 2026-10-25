import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { StatusHistory } from '@/app/components/status-history';
import type { EventStatusHistory } from '@/lib/event-requests';

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => navigation }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

// AC5-X1 (cross-cutting): normal history distinguishes actual automatic completion from manual completion without losing actor, time or refresh behaviour.
test('labels only the recorded automatic completion source', () => {
  const automatic: EventStatusHistory = {
    id: 40, event_request_id: '40000000-0000-4000-8000-000000000001',
    previous_status: 'Confirmed', new_status: 'Completed', actor_id: null,
    actor_role: 'system', source: 'event_request.auto_completed',
    entry_kind: 'transition', occurred_at: '2026-10-23T04:00:01Z',
  };
  const before = structuredClone(automatic);
  const view = render(<StatusHistory entries={[automatic]} />);
  const activity = within(screen.getByRole('list', { name: 'Event status activity' }));
  expect(activity.getByText('Completed automatically')).toBeDefined();
  expect(activity.getByText('Confirmed → Completed')).toBeDefined();
  expect(activity.getByText('System')).toBeDefined();
  expect(activity.getByRole('listitem').querySelector('time')?.dateTime).toBe(automatic.occurred_at);
  expect(navigation.refresh).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Refresh status and history' }));
  expect(navigation.refresh).toHaveBeenCalledTimes(1);
  expect(automatic).toEqual(before);

  view.rerender(<StatusHistory entries={[{ ...automatic, actor_id: 'coordinator-1',
    actor_role: 'event_coordinator', source: 'coordinator.completion' }]} />);
  expect(screen.queryByText('Completed automatically')).toBeNull();
  expect(screen.getByText('Confirmed → Completed')).toBeDefined();
  expect(screen.getByText(/Event Coordinator.*coordinator-1/)).toBeDefined();
});
