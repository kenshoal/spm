import { afterEach, expect, test, vi } from 'vitest';
import { markArrangementReviewed } from '@/app/arrangement-reviews/actions';
import { clearArrangementReview } from '@/lib/arrangement-reviews';
import { requireRole } from '@/lib/auth';
import { revalidatePath } from 'next/cache';

vi.mock('@/lib/auth', () => ({ requireRole: vi.fn(async () => ({})) }));
vi.mock('@/lib/arrangement-reviews', async original => ({ ...await original<typeof import('@/lib/arrangement-reviews')>(), clearArrangementReview: vi.fn() }));
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
afterEach(() => vi.clearAllMocks());
const checked = () => { const data = new FormData(); data.set('reviewed', 'on'); return data; };

// AC4-X3 (cross-cutting): a forged unchecked submission cannot bypass the staff acknowledgement requirement.
test('unchecked clear authenticates domain and performs no API mutation', async () => {
  expect(await markArrangementReviewed('T1', 'venue_booking', {}, new FormData())).toEqual({ message: 'Confirm that you have checked the referenced arrangement first.' });
  expect(requireRole).toHaveBeenCalledExactlyOnceWith('venue_staff');
  expect(clearArrangementReview).not.toHaveBeenCalled();
  expect(revalidatePath).not.toHaveBeenCalled();
});

// AC4-N6, AC4-N7 (negative): stale or failed clears retain explicit recovery feedback and never redirect as a saved acknowledgement.
test.each([
  { id: 'AC4-N6', status: 409, message: /already been marked.*Refresh the queue/i },
  { id: 'AC4-N7', status: 502, message: /could not be saved.*try again/i },
])('$id refuses false successful clearing', async ({ status, message }) => {
  vi.mocked(clearArrangementReview).mockResolvedValueOnce(new Response('{}', { status }));
  const result = await markArrangementReviewed('T1', 'equipment_reservation', {}, checked());
  expect(result.message).toMatch(message);
  expect(requireRole).toHaveBeenCalledExactlyOnceWith('technical_support');
  expect(clearArrangementReview).toHaveBeenCalledExactlyOnceWith('T1');
  expect(revalidatePath).not.toHaveBeenCalled();
});

// AC5-N5 (negative): a server-reported expired clear session preserves the normal authentication redirect.
test('clear401 redirects to authentication without success revalidation', async () => {
  vi.mocked(clearArrangementReview).mockResolvedValueOnce(new Response('{}', { status: 401 }));
  await expect(markArrangementReviewed('T1', 'venue_booking', {}, checked())).rejects.toMatchObject({ digest: expect.stringContaining('NEXT_REDIRECT;replace;/auth;307;') });
  expect(revalidatePath).not.toHaveBeenCalled();
});
