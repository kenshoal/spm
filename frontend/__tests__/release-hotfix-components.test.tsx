import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/coordination/requests/[id]/check-in-button", () => ({
  CheckInButton: ({ registrationId }: { registrationId: string }) => <button>Check in {registrationId}</button>,
}));

import { RegistrationTable } from "@/app/components/registration-table";
import type { EventRegistration } from "@/lib/registration-info";

afterEach(cleanup);

const row = (id: string, email: string | null, extra: Partial<EventRegistration> = {}): EventRegistration => ({
  id,
  attendee_id: `attendee-${id}`,
  attendee_email: email,
  status: "Registered",
  created_at: "2026-11-01T00:00:00Z",
  registered_by: null,
  attended_at: null,
  checked_in_by: null,
  ...extra,
});

// AC16-H2 (happy, hotfix 16): staff see each attendee's email instead of an account id
test("shows the attendee's email", () => {
  render(<RegistrationTable eventRequestId="e1" registrations={[row("1", "ann@example.com")]} canCheckIn={false} />);

  expect(screen.getByText("ann@example.com")).toBeDefined();
  expect(screen.queryByText("attendee-1")).toBeNull();
});

// AC16-N2 (negative, hotfix 16): with no email the account id still identifies the row
test("falls back to the account id when there is no email", () => {
  render(<RegistrationTable eventRequestId="e1" registrations={[row("1", null)]} canCheckIn={false} />);

  expect(screen.getByText("attendee-1")).toBeDefined();
});

// AC16-H3 (happy, hotfix 16): searching narrows the list to the matching attendee
test("finds an attendee by email at the counter", () => {
  render(<RegistrationTable eventRequestId="e1" registrations={[row("1", "ann@example.com"), row("2", "bob@example.com")]} canCheckIn />);

  fireEvent.change(screen.getByLabelText("Find an attendee"), { target: { value: "BOB" } });

  expect(screen.queryByText("ann@example.com")).toBeNull();
  expect(screen.getByText("bob@example.com")).toBeDefined();
});

// AC16-N3 (negative, hotfix 16): a search nobody matches says so
test("says when no attendee matches", () => {
  render(<RegistrationTable eventRequestId="e1" registrations={[row("1", "ann@example.com")]} canCheckIn />);

  fireEvent.change(screen.getByLabelText("Find an attendee"), { target: { value: "zzz" } });

  expect(screen.getByText("No attendee matches that search.")).toBeDefined();
});

// AC16-X1 (cross-cutting, hotfix 16): check-in is offered only to staff, for registered, unchecked rows
test("offers check-in only where it is allowed", () => {
  const rows = [row("1", "a@x.com"), row("2", "b@x.com", { attended_at: "2026-11-01T01:00:00Z" }), row("3", "c@x.com", { status: "Withdrawn" })];
  const { rerender } = render(<RegistrationTable eventRequestId="e1" registrations={rows} canCheckIn />);

  expect(screen.getAllByRole("button")).toHaveLength(1);

  rerender(<RegistrationTable eventRequestId="e1" registrations={rows} canCheckIn={false} />);

  expect(screen.queryAllByRole("button")).toHaveLength(0);
});

import { EventDetailsForm } from "@/app/coordination/requests/[id]/event-details-form";
import type { EventRequest } from "@/lib/event-requests";

vi.mock("@/app/coordination/requests/[id]/event-setup-actions", () => ({
  saveEventDetails: vi.fn(),
  saveRegistrationSettings: vi.fn(),
  recordEquipmentRequirement: vi.fn(),
  offerWaitlistPlace: vi.fn(),
}));

const event = {
  id: "e1",
  event_name: "Annual Gala",
  purpose: "Raise funds",
  description: "A dinner",
  proposed_date_times: ["2026-12-10T02:00:00Z"],
  expected_attendance: 100,
  venue_requirements: "Hall",
  accessibility_needs: "Ramp",
  equipment_requirements: "Mic",
  registration_needs: "Yes",
  updated_at: "2026-11-01T00:00:00Z",
} as unknown as EventRequest;

// AC8-X1 (cross-cutting, hotfix 8): the event's text is not repeated on the page until editing starts
test("shows no form fields until the coordinator chooses to edit", () => {
  render(<EventDetailsForm request={event} />);

  expect(screen.queryByText("Annual Gala")).toBeNull();
  expect(screen.queryByRole("textbox")).toBeNull();
});

// AC8-H5 (happy, hotfix 8): editing offers every detail, dates in Singapore time, with the version seen
test("opens an edit form with the stored values and the version it was loaded at", () => {
  const { container } = render(<EventDetailsForm request={event} />);

  fireEvent.click(screen.getByRole("button", { name: "Edit details" }));

  expect((screen.getByLabelText("Date and time 1") as HTMLInputElement).value).toBe("2026-12-10T10:00");
  expect((container.querySelector('input[name="expected_updated_at"]') as HTMLInputElement).value).toBe("2026-11-01T00:00:00Z");
  expect(screen.getByText("Annual Gala")).toBeDefined();
});
