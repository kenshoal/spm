import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { describeNotification, type AppNotification } from '@/lib/notifications';
import { NotificationList } from '@/app/notifications/notification-list';

vi.mock('@/app/notifications/actions', () => ({ markNotificationRead: vi.fn() }));
afterEach(cleanup);
const notification: AppNotification = {
  id: 'n-review', event_type: 'arrangement_needs_review', read_at: '2026-10-16T02:00:00Z',
  created_at: '2026-10-16T01:00:00Z', payload: {
    event_request_id: '64000000-0000-4000-8000-000000000100',
    arrangement: 'venue_booking', arrangement_id: '64000000-0000-4000-8000-000000000200',
    reason: 'Attendance changed from 25 to 40', trigger_type: 'event_change',
    href: 'https://attacker.invalid/do-not-follow',
  },
};

// AC3-X6, AC3-X7, AC3-X8, AC3-N5 (partition): verified capabilities choose only the matching internal destination, never payload.href.
test.each([
  { id: 'AC3-X6', arrangement: 'venue_booking', roles: ['venue_staff', 'event_coordinator'], href: '/arrangement-reviews?arrangement=venue_booking', label: /venue booking/i },
  { id: 'AC3-X7', arrangement: 'equipment_reservation', roles: ['technical_support'], href: '/arrangement-reviews?arrangement=equipment_reservation', label: /equipment reservation/i },
  { id: 'AC3-X8', arrangement: 'venue_booking', roles: ['event_coordinator'], href: '/coordination/requests/64000000-0000-4000-8000-000000000100', label: /venue booking/i },
  { id: 'AC3-N5', arrangement: 'venue_booking', roles: ['technical_support'], href: null, label: /venue booking/i },
])('$id actionable review notice uses current verified roles', ({ arrangement, roles, href, label }) => {
  const input = { ...notification, payload: { ...notification.payload, arrangement } };
  const before = structuredClone(input);
  const summary = describeNotification(input, roles);
  expect(summary.message).toMatch(label);
  expect(`${summary.message} ${summary.detail}`).toMatch(/review/i);
  expect(summary.detail).toContain(notification.payload.reason);
  expect(summary.detail).toContain(notification.payload.arrangement_id);
  expect(summary.href).toBe(href);
  expect(input).toEqual(before);
});

// AC3-X6 (cross-cutting): the inbox forwards verified role context into actionable review cards while legacy callers remain valid.
test('inbox renders recorded reason and role-scoped destination', () => {
  render(<NotificationList notifications={[notification]} roles={['venue_staff']} />);
  expect(screen.getByText(/Attendance changed from 25 to 40/)).toBeDefined();
  expect(screen.getByRole('link', { name: 'View request' }).getAttribute('href')).toBe('/arrangement-reviews?arrangement=venue_booking');
  expect(screen.queryByRole('link', { name: /attacker/i })).toBeNull();
});
