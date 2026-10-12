import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { StatusHistory } from '@/app/components/status-history';
import { getEventRequestStatusView, listStatusHistory } from '@/lib/event-requests';

vi.mock('next/navigation', async importOriginal => ({
  ...await importOriginal<typeof import('next/navigation')>(),
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock('@/lib/auth', () => ({ requireAccessToken: vi.fn(async () => 'history-session') }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const systemEntry = {
  id: 3, event_request_id: 'event/1', previous_status: 'Confirmed', new_status: 'Completed',
  actor_id: null, actor_role: 'system', source: 'scheduled.completion', entry_kind: 'transition',
  occurred_at: '2026-10-10T02:00:00Z',
};

// AC2-X2 (cross-cutting): the server lookup preserves recorded system attribution and uses a fresh, scoped read
test('retains all fields through an encoded authenticated history lookup', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify([systemEntry]), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  expect(await listStatusHistory('event/1')).toEqual([systemEntry]);
  expect(fetch).toHaveBeenCalledExactlyOnceWith(
    expect.stringContaining('/event-requests/event%2F1/status-history'),
    { headers: { Authorization: 'Bearer history-session' }, cache: 'no-store' },
  );
});

const initialRequest = {
  id: 'event-1', organiser_id: 'owner', event_name: 'Original event', purpose: 'Original purpose',
  status: 'Submitted', created_at: '2026-10-10T01:00:00Z', updated_at: '2026-10-10T01:00:00Z',
};
const currentRequest = { ...initialRequest, status: 'Under Review', event_name: 'Current event',
  purpose: 'Current purpose', updated_at: '2026-10-10T02:00:00Z' };
const reviewEntry = { ...systemEntry, event_request_id: 'event-1', previous_status: 'Submitted',
  new_status: 'Under Review', actor_id: 'coordinator', actor_role: 'event_coordinator', source: 'coordinator.review' };
const approvalEntry = { ...reviewEntry, id: 4, previous_status: 'Under Review', new_status: 'Approved' };
const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function mockResponses(...responses: Response[]) {
  const fetch = vi.fn<typeof globalThis.fetch>();
  for (const response of responses) fetch.mockResolvedValueOnce(response);
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

// AC7-N2 (negative): relationship revocation cannot be reported as a successful empty timeline
test('revoked history access becomes an unavailable panel rather than empty success', async () => {
  mockResponses(jsonResponse(initialRequest), jsonResponse({ detail: { code: 'HISTORY_NOT_FOUND' } }, 404));
  const view = await getEventRequestStatusView('event-1');
  expect(view).toEqual({ request: initialRequest, history: [], historyUnavailable: true, statusUnsettled: false });
  render(<StatusHistory entries={view.history} unavailable={view.historyUnavailable} />);
  expect(screen.getByRole('alert').textContent).toContain('Status history is temporarily unavailable');
  expect(screen.queryByText('No status history is available yet.')).toBeNull();
  expect(screen.queryAllByRole('listitem')).toHaveLength(0);
});

// AC5-N8 (negative): an expired server session keeps Next's real authentication redirect through the status-view catch
test('expired history authentication redirects instead of swallowing framework control flow', async () => {
  mockResponses(jsonResponse(initialRequest), jsonResponse({ detail: 'Invalid session' }, 401));
  await expect(getEventRequestStatusView('event-1')).rejects.toMatchObject({
    digest: expect.stringContaining('NEXT_REDIRECT;replace;/auth;307;'),
  });
  expect(screen.queryByRole('alert')).toBeNull();
});


// AC4-X7 (cross-cutting): reconciliation must refetch the complete event and history rather than guessing only the status
test('one concurrent transition returns a fresh whole request and matching unmodified history', async () => {
  const before = structuredClone({ initialRequest, currentRequest, reviewEntry });
  const fetch = mockResponses(jsonResponse(initialRequest), jsonResponse([reviewEntry]),
    jsonResponse(currentRequest), jsonResponse([reviewEntry]));
  const view = await getEventRequestStatusView('event-1');
  expect(view).toEqual({ request: currentRequest, history: [reviewEntry], historyUnavailable: false, statusUnsettled: false });
  expect(fetch).toHaveBeenCalledTimes(4);
  const retryEvent = fetch.mock.calls[2];
  const retryHistory = fetch.mock.calls[3];
  expect(retryEvent[0]).toEqual(expect.stringContaining('/event-requests/event-1'));
  expect(retryHistory[0]).toEqual(expect.stringContaining('/event-requests/event-1/status-history'));
  expect(retryEvent[1]?.signal).toBeInstanceOf(AbortSignal);
  expect(retryHistory[1]?.signal).toBe(retryEvent[1]?.signal);
  expect(retryEvent[1]?.cache).toBe('no-store');
  expect(retryHistory[1]?.cache).toBe('no-store');
  expect({ initialRequest, currentRequest, reviewEntry }).toEqual(before);
});

// AC4-N2 (negative): a continuing race must stop after one reconciliation and suppress contradictory history/state actions
test('a second mismatched snapshot is explicitly unsettled with bounded work', async () => {
  const fetch = mockResponses(jsonResponse(initialRequest), jsonResponse([reviewEntry]),
    jsonResponse(currentRequest), jsonResponse([approvalEntry]));
  const view = await getEventRequestStatusView('event-1');
  expect(view).toEqual({ request: currentRequest, history: [], historyUnavailable: true, statusUnsettled: true });
  expect(fetch).toHaveBeenCalledTimes(4);
  expect(approvalEntry.new_status).toBe('Approved');
});

// AC4-N3 (negative): losing the fresh event read cannot fall back to status-dependent controls from the stale event
test('event refetch failure retains a warning state and refuses to claim settled history', async () => {
  const fetch = mockResponses(jsonResponse(initialRequest), jsonResponse([reviewEntry]),
    jsonResponse({ detail: 'Event service unavailable' }, 502));
  expect(await getEventRequestStatusView('event-1')).toEqual({
    request: initialRequest, history: [], historyUnavailable: true, statusUnsettled: true,
  });
  expect(fetch).toHaveBeenCalledTimes(3);
});

// AC4-N4 (negative): a failed second history read must retain unresolved-state safeguards rather than an empty success
test('history refetch failure retains the fresh event with unsettled status', async () => {
  const fetch = mockResponses(jsonResponse(initialRequest), jsonResponse([reviewEntry]),
    jsonResponse(currentRequest), jsonResponse({ detail: 'History unavailable' }, 502));
  expect(await getEventRequestStatusView('event-1')).toEqual({
    request: currentRequest, history: [], historyUnavailable: true, statusUnsettled: true,
  });
  expect(fetch).toHaveBeenCalledTimes(4);
});

// AC5-N10 (negative): disappearing access during reconciliation must discard previously read protected history
test('a revoked event on refetch becomes not found without retaining history', async () => {
  const fetch = mockResponses(jsonResponse(initialRequest), jsonResponse([reviewEntry]),
    jsonResponse({ detail: 'Event request not found' }, 404));
  expect(await getEventRequestStatusView('event-1')).toEqual({
    request: null, history: [], historyUnavailable: false, statusUnsettled: false,
  });
  expect(fetch).toHaveBeenCalledTimes(3);
});

for (const scenario of [
  { id: 'AC5-N11', stage: 'event', responses: [jsonResponse(initialRequest), jsonResponse([reviewEntry]), jsonResponse({ detail: 'Invalid session' }, 401)] },
  { id: 'AC5-N12', stage: 'history', responses: [jsonResponse(initialRequest), jsonResponse([reviewEntry]), jsonResponse(currentRequest), jsonResponse({ detail: 'Invalid session' }, 401)] },
]) {
  // AC5-N11, AC5-N12 (negative): authentication redirects during either fresh read must escape the reconciliation catch
  test(`${scenario.id} session expiry during retry ${scenario.stage} preserves the real redirect`, async () => {
    const fetch = mockResponses(...scenario.responses);
    await expect(getEventRequestStatusView('event-1')).rejects.toMatchObject({
      digest: expect.stringContaining('NEXT_REDIRECT;replace;/auth;307;'),
    });
    expect(fetch).toHaveBeenCalledTimes(scenario.responses.length);
  });
}


// AC4-N5 (negative): an ordinary history outage does not make the event itself uncertain or disable its established workflow
test('initial history outage preserves the complete event and normal status branch', async () => {
  const fetch = mockResponses(jsonResponse(initialRequest), jsonResponse({ detail: 'History unavailable' }, 502));
  expect(await getEventRequestStatusView('event-1')).toEqual({
    request: initialRequest, history: [], historyUnavailable: true, statusUnsettled: false,
  });
  expect(fetch).toHaveBeenCalledTimes(2);
});

// AC5-N13 (negative): a nonexistent or inaccessible event must stop before requesting protected history
test('initial event not found returns no request or history and skips history lookup', async () => {
  const fetch = mockResponses(jsonResponse({ detail: 'Event request not found' }, 404));
  expect(await getEventRequestStatusView('event-1')).toEqual({
    request: null, history: [], historyUnavailable: false, statusUnsettled: false,
  });
  expect(fetch).toHaveBeenCalledTimes(1);
});
