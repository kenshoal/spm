import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { ArrangementReviewPanel } from '@/app/components/arrangement-review-panel';
import { ClearReviewForm } from '@/app/arrangement-reviews/clear-review-form';
import { listEventArrangementReviews } from '@/lib/arrangement-reviews';
import { markArrangementReviewed } from '@/app/arrangement-reviews/actions';

vi.mock('@/lib/arrangement-reviews', async original => ({ ...await original<typeof import('@/lib/arrangement-reviews')>(), listEventArrangementReviews: vi.fn() }));
vi.mock('@/app/arrangement-reviews/actions', () => ({ markArrangementReviewed: vi.fn() }));
vi.mock('next/navigation', async original => ({ ...await original<typeof import('next/navigation')>(), useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

// AC5-B1 (boundary): a successful empty coordinator view is visibly clear and offers no staff mutation.
test('empty review panel is an honest empty result', async () => {
  vi.mocked(listEventArrangementReviews).mockResolvedValueOnce([]);
  render(await ArrangementReviewPanel({ eventId: 'event-1' }));
  expect(screen.getByRole('region', { name: 'Outstanding arrangement reviews' })).toBeDefined();
  expect(screen.getByText('No outstanding arrangement reviews')).toBeDefined();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Mark reviewed' })).toBeNull();
  expect(listEventArrangementReviews).toHaveBeenCalledExactlyOnceWith('event-1');
});

// AC5-N3 (negative): a failed protected lookup cannot tell the coordinator that every review is clear.
test('unavailable review lookup shows recovery instead of empty success', async () => {
  vi.mocked(listEventArrangementReviews).mockRejectedValueOnce(new Error('private storage failure'));
  render(await ArrangementReviewPanel({ eventId: 'event-1' }));
  expect(screen.getByRole('alert').textContent).toMatch(/temporarily unavailable/i);
  expect(screen.getByRole('button', { name: 'Refresh reviews' })).toBeDefined();
  expect(screen.queryByText('No outstanding arrangement reviews')).toBeNull();
  expect(screen.queryByText(/private storage failure/)).toBeNull();
});

// AC5-N5 (negative): expired authentication keeps the real framework redirect rather than an outage/empty panel.
test('authentication redirect escapes panel recovery', async () => {
  const { redirect } = await import('next/navigation');
  let control: unknown;
  try { redirect('/auth'); } catch (error) { control = error; }
  vi.mocked(listEventArrangementReviews).mockRejectedValueOnce(control);
  await expect(ArrangementReviewPanel({ eventId: 'event-1' })).rejects.toBe(control);
  expect(screen.queryByRole('alert')).toBeNull();
});

// AC4-X3 (cross-cutting): acknowledgement is explicit and a pending exact-row clear cannot be submitted twice.
test('acknowledgement and pending state protect the staff clear action', async () => {
  let finish!: (result: { message: string }) => void;
  vi.mocked(markArrangementReviewed).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<ClearReviewForm reviewId='review-T1' arrangement='venue_booking' />);
  const checkbox = screen.getByRole('checkbox', { name: 'I have checked this arrangement against the recorded change' }) as HTMLInputElement;
  const button = screen.getByRole('button', { name: 'Mark reviewed' }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.click(checkbox);
  expect(button.disabled).toBe(false);
  fireEvent.submit(button.closest('form')!);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Saving…' })).toBeDefined());
  expect(checkbox.disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Saving…' }) as HTMLButtonElement).disabled).toBe(true);
  expect(markArrangementReviewed).toHaveBeenCalledTimes(1);
  expect(vi.mocked(markArrangementReviewed).mock.calls[0].slice(0, 2)).toEqual(['review-T1', 'venue_booking']);
  await act(async () => { finish({ message: 'This review has already been marked. Refresh the queue.' }); });
  expect(screen.getByRole('alert').textContent).toMatch(/already been marked/i);
  expect(checkbox.disabled).toBe(false);
});
