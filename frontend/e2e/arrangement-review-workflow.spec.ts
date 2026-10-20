import { expect, test } from '@playwright/test';

const API = 'http://127.0.0.1:8103';
const VENUE_API = 'http://127.0.0.1:8105';
const venue = '64000000-0000-4000-8000-000000000011';
const equipment = '64000000-0000-4000-8000-000000000012';
const reviews = [
  { id: '64000000-0000-4000-8000-000000000101', arrangement: 'venue_booking', arrangement_id: venue, trigger_id: '64000000-0000-4000-8000-000000000201', trigger_type: 'event_change', changed_fields: ['expected_attendance'], reason: 'Old venue reason: attendance changed from 25 to 40', raised_at: '2026-10-15T01:00:00Z' },
  { id: '64000000-0000-4000-8000-000000000102', arrangement: 'venue_booking', arrangement_id: venue, trigger_id: '64000000-0000-4000-8000-000000000202', trigger_type: 'safety_recheck', changed_fields: [], reason: 'Later venue reason: recheck emergency access', raised_at: '2026-10-16T01:00:00Z' },
  { id: '64000000-0000-4000-8000-000000000103', arrangement: 'equipment_reservation', arrangement_id: equipment, trigger_id: '64000000-0000-4000-8000-000000000203', trigger_type: 'equipment_unavailable', changed_fields: ['operational_status'], reason: 'Equipment reason: microphone became DAMAGED', raised_at: '2026-10-16T02:00:00Z' },
];
const cookie = (value: string) => [{ name: 'cs_access_token', value, url: 'http://127.0.0.1:3100' }];

// AC5-X9 (cross-cutting): both merged coordinator panels retain cancelled/sibling booking facts while responsible staff clear only exact review causes.
test('coordinator sees retained later causes until each responsible domain rechecks', async ({ page, request }) => {
  const seeded = await request.post(`${API}/__seed`, { data: {
    event_name: 'SCRUM64 review UI critical journey', organiser_id: 'playwright-user',
    status: 'Planning', coordinator_id: 'playwright-coordinator', arrangement_reviews: [reviews[2], reviews[1], reviews[0]],
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  const headers = { Authorization: 'Bearer coordinator-session' };
  const cancelledVenue = await request.post(`${VENUE_API}/__seed`, { data: { name: `Cancelled review hall ${event.id}`, location: `Review wing ${event.id}`, max_capacity: 100 } });
  const siblingVenue = await request.post(`${VENUE_API}/__seed`, { data: { name: `Approved sibling hall ${event.id}`, location: `Sibling wing ${event.id}`, max_capacity: 100 } });
  expect(cancelledVenue.status()).toBe(201);
  expect(siblingVenue.status()).toBe(201);
  const cancelledVenueData = await cancelledVenue.json();
  const siblingVenueData = await siblingVenue.json();
  for (const booking of [
    { id: venue, venue_id: cancelledVenueData.id, status: 'cancelled', cancelled_by: 'playwright-coordinator', cancelled_at: '2026-10-17T01:00:00Z' },
    { id: '64000000-0000-4000-8000-000000000013', venue_id: siblingVenueData.id, status: 'approved', cancelled_by: null, cancelled_at: null },
  ]) {
    const bookingSeed = await request.post(`${VENUE_API}/__seed_booking`, { data: {
      ...booking, event_request_id: event.id, requested_by: 'playwright-coordinator',
      start_date: '2026-11-20', end_date: '2026-11-20', slots: ['AM'],
      decided_by: 'playwright-venue-staff', decided_at: '2026-10-16T01:00:00Z',
    } });
    expect(bookingSeed.status()).toBe(201);
  }
  const bookingResponse = await request.get(`${VENUE_API}/booking-requests/event/${event.id}`, { headers });
  expect(bookingResponse.status()).toBe(200);
  const bookingSnapshot = await bookingResponse.json();
  expect(bookingSnapshot).toHaveLength(2);
  const historyResponse = await request.get(`${API}/event-requests/${event.id}/status-history`, { headers });
  expect(historyResponse.status()).toBe(200);
  const history = await historyResponse.json();
  expect(history).toHaveLength(1);
  await page.context().addCookies(cookie('coordinator-session'));
  await page.goto(`/coordination/requests/${event.id}`);
  const panel = page.getByRole('region', { name: 'Outstanding arrangement reviews' });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('listitem')).toHaveCount(3);
  const bookings = page.getByRole('region', { name: 'Venue bookings' });
  await expect(bookings.getByRole('listitem')).toHaveCount(2);
  const cancelledBooking = bookings.getByRole('listitem').filter({ hasText: cancelledVenueData.name });
  await expect(cancelledBooking).toContainText('Cancelled');
  await expect(cancelledBooking.getByRole('button', { name: /Cancel booking/ })).toHaveCount(0);
  await expect(bookings.getByRole('listitem').filter({ hasText: siblingVenueData.name })).toContainText('Approved');
  for (const row of reviews) {
    await expect(panel.getByText(row.reason, { exact: true })).toBeVisible();
    await expect(panel.getByText(row.arrangement_id, { exact: false }).first()).toBeVisible();
  }
  await expect(panel.getByRole('button', { name: 'Mark reviewed', exact: true })).toHaveCount(0);

  for (const step of [
    { session: 'venue-session', domain: 'venue_booking', row: reviews[0], remaining: 2, queueCount: 2 },
    { session: 'tech-session', domain: 'equipment_reservation', row: reviews[2], remaining: 1, queueCount: 1 },
    { session: 'venue-session', domain: 'venue_booking', row: reviews[1], remaining: 0, queueCount: 1 },
  ]) {
    await page.context().addCookies(cookie(step.session));
    await page.goto(`/arrangement-reviews?arrangement=${step.domain}`);
    const queue = page.getByRole('region', { name: 'Arrangement review queue' });
    await expect(queue.getByRole('listitem')).toHaveCount(step.queueCount);
    const row = queue.getByRole('listitem').filter({ hasText: step.row.reason });
    await expect(row).toHaveCount(1);
    const mark = row.getByRole('button', { name: 'Mark reviewed', exact: true });
    await expect(mark).toBeDisabled();
    await row.getByRole('checkbox', { name: 'I have checked this arrangement against the recorded change', exact: true }).check();
    await expect(mark).toBeEnabled();
    await mark.click();
    await expect(queue.getByText(step.row.reason, { exact: true })).toHaveCount(0);
    await page.context().addCookies(cookie('coordinator-session'));
    await page.goto(`/coordination/requests/${event.id}`);
    await page.reload();
    await expect(panel.getByRole('listitem')).toHaveCount(step.remaining);
    await expect(bookings.getByRole('listitem')).toHaveCount(2);
    await expect(cancelledBooking).toContainText('Cancelled');
    await expect(bookings.getByRole('listitem').filter({ hasText: siblingVenueData.name })).toContainText('Approved');
    if (step.remaining === 2) await expect(panel.getByText(reviews[1].reason, { exact: true })).toBeVisible();
  }
  await expect(panel.getByText('No outstanding arrangement reviews', { exact: false })).toBeVisible();
  const persisted = await request.get(`${API}/event-requests/${event.id}`, { headers });
  expect(persisted.status()).toBe(200);
  expect(await persisted.json()).toEqual(event);
  const finalHistory = await request.get(`${API}/event-requests/${event.id}/status-history`, { headers });
  expect(finalHistory.status()).toBe(200);
  expect(await finalHistory.json()).toEqual(history);
  const finalBookings = await request.get(`${VENUE_API}/booking-requests/event/${event.id}`, { headers });
  expect(finalBookings.status()).toBe(200);
  expect(await finalBookings.json()).toEqual(bookingSnapshot);
});
