import { expect, test } from '@playwright/test';

const API = 'http://127.0.0.1:8103';
const cookie = (value: string) => [{ name: 'cs_access_token', value, url: 'http://127.0.0.1:3100' }];

// AC5-X1 (cross-cutting): coordinator end recording survives reload and both normal readers display an explicit prepared automatic completion without organiser edit access.
test('records final end and refreshes normal views to automatic completion', async ({ page, request }) => {
  const seeded = await request.post(`${API}/__seed`, { data: {
    event_name: 'SCRUM-40 final end and completion visibility', purpose: 'Verify normal workflow projection',
    description: 'Prepared UI records; actual completion is verified separately in PostgreSQL.',
    organiser_id: 'playwright-user', coordinator_id: 'playwright-coordinator', status: 'Planning',
    proposed_date_times: ['2026-11-25T02:00:00Z'], expected_attendance: 40,
    venue_requirements: 'Existing seminar room', equipment_requirements: 'Existing microphone',
    registration_needs: 'Existing online form', final_event_end_at: null,
    final_end_response: { final_event_end_at: '2026-11-25T10:30:00Z', updated_at: '2026-10-23T04:01:00Z' },
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  const read = () => request.get(`${API}/event-requests/${event.id}`, { headers: { Authorization: 'Bearer coordinator-session' } });
  const before = await (await read()).json();

  await page.context().addCookies(cookie('coordinator-session'));
  await page.goto(`/coordination/requests/${event.id}`);
  const end = page.getByRole('region', { name: 'Final event end', exact: true });
  await expect(end).toBeVisible();
  await end.getByLabel('Final event end (Singapore time)', { exact: true }).fill('2026-11-25T18:30');
  await end.getByRole('button', { name: 'Save final event end', exact: true }).click();
  await expect.poll(async () => new Date((await (await read()).json()).final_event_end_at).toISOString()).toBe('2026-11-25T10:30:00.000Z');
  await page.reload();
  await expect(end.getByLabel('Final event end (Singapore time)', { exact: true })).toHaveValue('2026-11-25T18:30');
  const saved = await (await read()).json();
  expect({ ...saved, final_event_end_at: before.final_event_end_at, updated_at: before.updated_at }).toEqual(before);
  const historyBefore = await request.get(`${API}/event-requests/${event.id}/status-history`, { headers: { Authorization: 'Bearer coordinator-session' } });
  expect((await historyBefore.json()).map((entry: { new_status: string }) => entry.new_status)).toEqual(['Planning']);

  // The page must reconcile a backend-cleared end, not an unsupported unkeyed component rerender.
  const cleared = await request.post(`${API}/__prepare_event_projection`, { data: {
    event_request_id: event.id, event: { final_event_end_at: null },
  } });
  expect(cleared.status()).toBe(201);
  await page.getByRole('region', { name: 'Status history' }).getByRole('button', { name: 'Refresh status and history' }).click();
  await expect(end.getByLabel('Final event end (Singapore time)', { exact: true })).toHaveValue('');
  await expect(end.getByText('Final event end saved.', { exact: true })).toHaveCount(0);
  await end.getByLabel('Final event end (Singapore time)', { exact: true }).fill('2026-11-25T18:30');
  await end.getByRole('button', { name: 'Save final event end', exact: true }).click();
  await expect.poll(async () => new Date((await (await read()).json()).final_event_end_at).toISOString()).toBe('2026-11-25T10:30:00.000Z');

  await page.context().addCookies(cookie('test-session'));
  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(page.getByRole('button', { name: 'Save final event end', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Final event end (Singapore time)', { exact: true })).toHaveCount(0);
  const prepared = await request.post(`${API}/__prepare_event_projection`, { data: {
    event_request_id: event.id, event: { status: 'Completed', updated_at: '2026-12-03T10:30:01Z' },
    history: { previous_status: 'Confirmed', new_status: 'Completed', actor_id: null, actor_role: 'system',
      source: 'event_request.auto_completed', entry_kind: 'transition', occurred_at: '2026-12-03T10:30:01Z' },
  } });
  expect(prepared.status()).toBe(201);
  const timeline = page.getByRole('region', { name: 'Status history' });
  await timeline.getByRole('button', { name: 'Refresh status and history' }).click();
  await expect(timeline.getByText('Completed automatically', { exact: true })).toBeVisible();
  await expect(timeline.getByText('Confirmed → Completed', { exact: true })).toBeVisible();
  await expect(timeline.getByRole('listitem').first()).toContainText('System');
  await expect(timeline.getByRole('listitem').first().locator('time')).toHaveAttribute('datetime', '2026-12-03T10:30:01Z');
  await expect(page.getByRole('region', { name: 'Status progress' }).locator('[aria-current="step"]')).toContainText('Completed');
  await page.reload();
  await expect(timeline.getByText('Completed automatically', { exact: true })).toBeVisible();
  await page.context().addCookies(cookie('coordinator-session'));
  await page.goto(`/coordination/requests/${event.id}`);
  await expect(timeline.getByText('Completed automatically', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save final event end', exact: true })).toHaveCount(0);
  expect((await (await read()).json()).final_event_end_at).toBe(saved.final_event_end_at);
});
