import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { RegistrationReviewPanel } from "@/app/components/registration-review-panel";
import { acknowledgeRegistrationReview } from "@/app/coordination/actions";

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
vi.mock("@/app/coordination/actions", () => ({ acknowledgeRegistrationReview: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const eventId = "35000000-0000-4000-8000-000000000001";
const coordinatorId = "35000000-0000-4000-8000-000000000099";
const older = {
  id: "35000000-0000-4000-8000-000000000011", event_request_id: eventId,
  event_updated_at: "2026-10-22T10:00:00Z", changed_fields: ["expected_attendance"],
  reason: "Attendance changed from 25 to 40; review registration arrangements.",
  raised_at: "2026-10-22T10:00:01Z", cleared_at: null, cleared_by: null,
};
const newer = { ...older, id: "35000000-0000-4000-8000-000000000012", event_updated_at: "2026-10-22T10:10:00Z",
  raised_at: "2026-10-22T10:10:01Z", changed_fields: ["registration_needs"], reason: "Paper form changed to an accessible online form." };
const acknowledged = { ...older, id: "35000000-0000-4000-8000-000000000010", reason: "Earlier registration arrangement checked.",
  cleared_at: "2026-10-22T09:00:00Z", cleared_by: coordinatorId };

// AC3-X20 (cross-cutting): acknowledgement is deliberate, bound to the selected older cause and recoverable without clearing newer evidence.
test("coordinator checks and acknowledges exact registration review with pending and failure recovery", async () => {
  let finish!: (value: { message: string }) => void;
  vi.mocked(acknowledgeRegistrationReview).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const reviews = [newer, older, acknowledged];
  const before = structuredClone(reviews);
  render(<RegistrationReviewPanel eventRequestId={eventId} reviews={reviews} canAcknowledge />);
  expect(screen.getByRole("region", { name: "Registration reviews" })).toBeDefined();
  const article = screen.getByText(older.reason).closest("article");
  expect(article).not.toBeNull();
  const scope = within(article!);
  const button = scope.getByRole("button", { name: "Acknowledge registration review" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(acknowledgeRegistrationReview).not.toHaveBeenCalled();
  fireEvent.click(scope.getByRole("checkbox", { name: "I have checked the registration arrangements against this change" }));
  expect(button.disabled).toBe(false);
  fireEvent.click(button);
  await waitFor(() => expect(acknowledgeRegistrationReview).toHaveBeenCalledTimes(1));
  expect(vi.mocked(acknowledgeRegistrationReview).mock.calls[0].slice(0, 2)).toEqual([eventId, older.id]);
  expect(button.disabled).toBe(true);
  await act(async () => finish({ message: "Registration reviews unavailable" }));
  expect(scope.getByRole("alert").textContent).toContain("Registration reviews unavailable");
  expect(navigation.refresh).not.toHaveBeenCalled();
  vi.mocked(acknowledgeRegistrationReview).mockResolvedValueOnce({ acknowledged: true });
  fireEvent.click(scope.getByRole("button", { name: "Acknowledge registration review" }));
  await waitFor(() => expect(navigation.refresh).toHaveBeenCalledTimes(1));
  expect(screen.getByText(newer.reason)).toBeDefined();
  expect(screen.getByText(acknowledged.reason)).toBeDefined();
  expect(reviews).toEqual(before);
});

// AC3-X18 (cross-cutting): an organiser retains outstanding and acknowledged facts with actor/time while read access never becomes an acknowledgement control.
test("organiser sees retained registration history without acknowledgement controls", () => {
  render(<RegistrationReviewPanel eventRequestId={eventId} reviews={[newer, acknowledged]} />);
  const panel = screen.getByRole("region", { name: "Registration reviews" });
  expect(within(panel).getByText(newer.reason)).toBeDefined();
  expect(within(panel).getByText(acknowledged.reason)).toBeDefined();
  expect(panel.textContent).toContain("Outstanding");
  expect(panel.textContent).toContain("Acknowledged");
  expect(panel.textContent).toContain(coordinatorId);
  expect(Array.from(panel.querySelectorAll("time")).map(node => node.getAttribute("datetime"))).toContain(acknowledged.cleared_at);
  expect(within(panel).queryByRole("checkbox")).toBeNull();
  expect(within(panel).queryByRole("button", { name: "Acknowledge registration review" })).toBeNull();
  expect(acknowledgeRegistrationReview).not.toHaveBeenCalled();
});
