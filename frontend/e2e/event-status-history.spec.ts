import { expect, test } from '@playwright/test';

const API = 'http://127.0.0.1:8103';
const cookie = (value: string) => [{ name: 'cs_access_token', value, url: 'http://127.0.0.1:3100' }];
const payload = {
  event_name: 'SCRUM-48 Status History', purpose: 'Inspect status evidence', description: 'A history journey',
  proposed_date_times: ['2026-11-20T02:00:00Z'], expected_attendance: 40,
  venue_requirements: 'Seminar room', accessibility_needs: 'Step-free',
  equipment_requirements: 'No technical kit required', registration_needs: 'Online registration',
};

// AC7-H1 (happy): related readers see one retained entry per transition after navigation and reload
test('organiser and coordinator see newest-first status history', async ({ page, request }) => {
  const created = await request.post(`${API}/event-requests/submissions`, {
    headers: { Authorization: 'Bearer test-session' }, data: payload,
  });
  expect(created.status()).toBe(201);
  const event = await created.json();
  await page.context().addCookies(cookie('test-session'));
  await page.goto(`/event-requests/${event.id}/edit`);
  const timeline = page.getByRole('region', { name: 'Status history' });
  await expect(timeline.getByText('Created as Submitted')).toBeVisible();
  await expect(timeline.getByRole('listitem')).toHaveCount(1);
  const assigned = await request.post(`${API}/event-requests/${event.id}/coordinator`, {
    headers: { Authorization: 'Bearer ops-session' }, data: { coordinator_id: 'playwright-coordinator' },
  });
  expect(assigned.status()).toBe(201);
  await page.context().addCookies(cookie('coordinator-session'));
  await page.goto(`/coordination/requests/${event.id}`);
  await page.getByRole('button', { name: 'Start review' }).click();
  await expect(timeline.getByText('Submitted → Under Review')).toBeVisible();
  await expect(timeline.getByRole('listitem')).toHaveCount(2);
  await expect(timeline.getByText('Newest first')).toBeVisible();
  await expect(timeline.getByRole('listitem').first()).toContainText('Submitted → Under Review');
  await page.reload();
  await expect(timeline.getByRole('listitem')).toHaveCount(2);
  await page.context().addCookies(cookie('colleague-session'));
  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(timeline.getByText('Submitted → Under Review')).toBeVisible();
  await expect(page.getByText(/shared by another organiser/i)).toBeVisible();
  const before = await request.get(`${API}/event-requests/${event.id}/status-history`, {
    headers: { Authorization: 'Bearer test-session' },
  });
  expect(before.status()).toBe(200);
  const rows = await before.json();
  expect(rows.map((row: { new_status: string }) => row.new_status)).toEqual(['Submitted', 'Under Review']);
  expect(rows[1].actor_id).toBe('playwright-coordinator');
  const repeated = await request.post(`${API}/event-requests/${event.id}/review`, {
    headers: { Authorization: 'Bearer coordinator-session' },
  });
  expect(repeated.status()).toBe(409);
  expect((await repeated.json()).detail).toBe("Transition not allowed from the current status");
  const after = await request.get(`${API}/event-requests/${event.id}/status-history`, {
    headers: { Authorization: 'Bearer test-session' },
  });
  expect(await after.json()).toEqual(rows);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(timeline).toBeVisible();
  const bounds = await timeline.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await timeline.screenshot({ path: test.info().outputPath('status-history-mobile.png') });
});

// AC7-N1 (negative): history dependency failure stays visible while event details remain usable
test('history outage does not hide the event or look like empty history', async ({ page, request }) => {
  const seeded = await request.post(`${API}/__seed`, { data: {
    ...payload, event_name: 'SCRUM-48 History outage', organiser_id: 'playwright-user',
    status: 'Submitted', history_unavailable: true,
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  const unavailable = await request.get(`${API}/event-requests/${event.id}/status-history`, {
    headers: { Authorization: 'Bearer test-session' },
  });
  expect(unavailable.status()).toBe(502);
  expect((await unavailable.json()).detail).toBe('Status history unavailable');
  await page.context().addCookies(cookie('test-session'));
  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(page.getByRole('heading', { name: event.event_name })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Status history' }).getByRole('alert')).toContainText('Status history is temporarily unavailable');
  await expect(page.getByText('No status history is available yet.')).toHaveCount(0);
});


for (const scenario of [
  { id: 'AC4-X5', name: 'owner', session: 'test-session', path: 'event-requests', suffix: '/edit' },
  { id: 'AC4-X6', name: 'coordinator', session: 'coordinator-session', path: 'coordination/requests', suffix: '' },
]) {
  // AC4-X5, AC4-X6 (cross-cutting): a transition between detail and history reads must not make one rendered page contradict itself
  test(`${scenario.id} ${scenario.name} reconciles a transition between its detail and history reads`, async ({ page, request }) => {
    const seeded = await request.post(`${API}/__seed`, { data: {
      ...payload, event_name: `SCRUM-48 read interleaving ${scenario.name}`, organiser_id: 'playwright-user',
      status: 'Submitted', coordinator_id: 'playwright-coordinator', history_read_transition: 'Under Review',
    } });
    expect(seeded.status()).toBe(201);
    const event = await seeded.json();
    await page.context().addCookies(cookie(scenario.session));
    await page.goto(`/${scenario.path}/${event.id}${scenario.suffix}`);
    const timeline = page.getByRole('region', { name: 'Status history' });
    await expect(timeline.getByText('Submitted → Under Review')).toBeVisible();
    const persisted = await request.get(`${API}/event-requests/${event.id}`, {
      headers: { Authorization: `Bearer ${scenario.session}` },
    });
    expect(persisted.status()).toBe(200);
    expect((await persisted.json()).status).toBe('Under Review');
    await expect(page.getByRole('region', { name: 'Status progress' }).locator('[aria-current="step"]')).toContainText('Under Review');
    if (scenario.name === 'coordinator') {
      await expect(page.getByRole('button', { name: 'Start review' })).toHaveCount(0);
    }
  });
}


// AC7-X2 (cross-cutting): explicit refresh reconciles the whole server view after another actor transitions the event.
test('AC7-X2 manual refresh updates both current status and newest activity', async ({ page, request }) => {
  const submitted = await request.post(`${API}/event-requests/submissions`, {
    headers: { Authorization: 'Bearer test-session' },
    data: { ...payload, event_name: 'SCRUM-48 manual refresh' },
  });
  expect(submitted.status()).toBe(201);
  const event = await submitted.json();
  const assigned = await request.post(`${API}/event-requests/${event.id}/coordinator`, {
    headers: { Authorization: 'Bearer ops-session' }, data: { coordinator_id: 'playwright-coordinator' },
  });
  expect(assigned.status()).toBe(201);
  await page.context().addCookies(cookie('test-session'));
  await page.goto(`/event-requests/${event.id}/edit`);
  const timeline = page.getByRole('region', { name: 'Status history' });
  const current = page.getByRole('region', { name: 'Status progress' }).locator('[aria-current="step"]');
  await expect(current).toContainText('Submitted');
  await expect(timeline.getByRole('listitem')).toHaveCount(1);
  const reviewed = await request.post(`${API}/event-requests/${event.id}/review`, {
    headers: { Authorization: 'Bearer coordinator-session' },
  });
  expect(reviewed.status()).toBe(200);
  const before = await request.get(`${API}/event-requests/${event.id}/status-history`, {
    headers: { Authorization: 'Bearer test-session' },
  });
  expect(before.status()).toBe(200);
  const rows = await before.json();
  expect(rows.map((row: { new_status: string }) => row.new_status)).toEqual(['Submitted', 'Under Review']);
  await expect(current).toContainText('Submitted');
  await timeline.getByRole('button', { name: 'Refresh status and history' }).click();
  await expect(current).toContainText('Under Review');
  await expect(timeline.getByRole('listitem')).toHaveCount(2);
  await expect(timeline.getByRole('listitem').first()).toContainText('Submitted → Under Review');
  await expect(timeline.getByRole('listitem').last()).toContainText('Created as Submitted');
  const after = await request.get(`${API}/event-requests/${event.id}/status-history`, {
    headers: { Authorization: 'Bearer test-session' },
  });
  expect(after.status()).toBe(200);
  expect(await after.json()).toEqual(rows);
});
