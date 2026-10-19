import { expect, test } from '@playwright/test';

const API = 'http://127.0.0.1:8103';

// AC5-X8 (cross-cutting): the real coordinator page preserves the Safety Review tracker across reload without granting a Confirm action.
test('Safety Review coordinator detail retains the complete journey without confirmation', async ({ page, request }) => {
  const seeded = await request.post(`${API}/__seed`, { data: {
    event_name: 'SCRUM-64 Safety Review browser compatibility',
    organiser_id: 'playwright-user', status: 'Safety Review',
    coordinator_id: 'playwright-coordinator', expected_attendance: 25,
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  const headers = { Authorization: 'Bearer coordinator-session' };
  const initialHistory = await request.get(`${API}/event-requests/${event.id}/status-history`, { headers });
  expect(initialHistory.status()).toBe(200);
  const history = await initialHistory.json();
  expect(history).toHaveLength(1);
  expect(history[0].new_status).toBe('Safety Review');
  await page.context().addCookies([
    { name: 'cs_access_token', value: 'coordinator-session', url: 'http://127.0.0.1:3100' },
  ]);
  await page.goto(`/coordination/requests/${event.id}`);
  const journey = page.getByRole('list', { name: 'Full event journey' });
  const stages = journey.getByRole('listitem');
  await expect(page.getByRole('heading', { name: event.event_name })).toBeVisible();
  await expect(stages).toHaveCount(8);
  await expect(stages).toHaveText([
    /Completed stage: Draft/, /Completed stage: Submitted/,
    /Completed stage: Under Review/, /Completed stage: Approved/,
    /Completed stage: Planning/, /Current stage: Safety Review/,
    /Not reached yet: Confirmed/, /Not reached yet: Completed/,
  ]);
  await expect(journey.locator('[aria-current="step"]')).toContainText('Safety Review');
  await expect(page.getByRole('button', { name: /^Confirm/i })).toHaveCount(0);
  await page.reload();
  await expect(stages).toHaveCount(8);
  await expect(journey.locator('[aria-current="step"]')).toContainText('Safety Review');
  await expect(page.getByRole('button', { name: /^Confirm/i })).toHaveCount(0);
  const persisted = await request.get(`${API}/event-requests/${event.id}`, { headers });
  expect(persisted.status()).toBe(200);
  expect(await persisted.json()).toEqual(event);
  const finalHistory = await request.get(`${API}/event-requests/${event.id}/status-history`, { headers });
  expect(finalHistory.status()).toBe(200);
  expect(await finalHistory.json()).toEqual(history);
});
