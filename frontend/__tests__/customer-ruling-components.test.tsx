import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

const actions = vi.hoisted(() => ({
  decide: vi.fn(),
  postpone: vi.fn(),
  resume: vi.fn(),
  organiser: vi.fn(),
  essential: vi.fn(),
}));
vi.mock("@/app/coordination/actions", () => ({
  decideEventChangeRequest: vi.fn(),
  decideEventChangeRequestPartly: actions.decide,
  registerAttendee: vi.fn(),
  withdrawEventRequest: vi.fn(),
}));
vi.mock("@/app/coordination/requests/[id]/event-setup-actions", () => ({
  postponeEvent: actions.postpone,
  resumeEvent: actions.resume,
  changeOrganiser: actions.organiser,
  setRequirementEssential: actions.essential,
}));
vi.mock("next/navigation", async (original) => ({
  ...(await original<typeof import("next/navigation")>()),
  useRouter: () => ({ refresh: vi.fn() }),
}));

import { RefusedChanges } from "@/app/components/refused-changes";
import { StatusProgress } from "@/app/components/status-progress";
import { ChangeRequestPanel } from "@/app/coordination/requests/[id]/change-request-panel";
import { EssentialForm } from "@/app/coordination/requests/[id]/essential-form";
import {
  ChangeOrganiserForm,
  PostponeEventForm,
  ResumeEventForm,
} from "@/app/coordination/requests/[id]/lifecycle-forms";
import { ManualRegistrationForm } from "@/app/coordination/requests/[id]/manual-registration-form";
import { PartialChangeForm } from "@/app/coordination/requests/[id]/partial-change-form";
import { parsePartialDecision } from "@/lib/change-decision";
import type { EventChangeRequest } from "@/lib/event-requests";
import { describeNotification, type AppNotification } from "@/lib/notifications";
import { vipPlaces } from "@/lib/vip-places";

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const FIELDS = ["expected_attendance", "venue_requirements", "equipment_requirements"];

function form(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    for (const item of Array.isArray(value) ? value : [value]) data.append(key, item);
  }
  return data;
}

// AC20-H1 (happy, hotfix 20): accepted fields and the refused ones' reasons are read from the form
test("reads a partial decision", () => {
  const result = parsePartialDecision(
    form({ accept: ["expected_attendance"], reason__venue_requirements: " Too small ", reason__equipment_requirements: "None free" }),
    FIELDS,
  );

  expect(result).toEqual({
    decision: {
      accepted_fields: ["expected_attendance"],
      rejected_reasons: { venue_requirements: "Too small", equipment_requirements: "None free" },
    },
  });
});

// AC20-N1, AC20-N2, AC20-N3 (negative, hotfix 20): all, none or an unknown field is not a partial decision
test.each([
  ["accepting nothing", { }, /Accept at least one field/],
  ["accepting everything", { accept: FIELDS }, /Every field is accepted/],
  ["an unknown field", { accept: ["expected_attendance", "purpose"] }, /only fields from this request/],
])("refuses %s", (_name, fields, message) => {
  expect(parsePartialDecision(form(fields), FIELDS).message).toMatch(message);
});

// AC20-B1, AC20-B2 (boundary, hotfix 20): a reason of 2000 characters is accepted and 2001 is not
test.each([
  [2000, true],
  [2001, false],
])("a refusal reason of %i characters is accepted: %s", (length, accepted) => {
  const result = parsePartialDecision(
    form({ accept: ["expected_attendance", "venue_requirements"], reason__equipment_requirements: "r".repeat(length) }),
    FIELDS,
  );

  expect(Boolean(result.decision)).toBe(accepted);
});

const pending = (changes: EventChangeRequest["proposed_changes"]): EventChangeRequest => ({
  id: "c1", event_request_id: "e1", organiser_id: "o1", status: "Pending", explanation: "Needs more",
  proposed_changes: changes, base_event_updated_at: "2030-01-01T00:00:00Z", coordinator_id: null,
  decision_reason: null, created_at: "2030-01-01T00:00:00Z", decided_at: null,
});

// AC20-H2 (happy, hotfix 20): a request with several fields offers the partial decision
test("offers to accept some changes when a request has several fields", () => {
  render(<ChangeRequestPanel requests={[pending({ expected_attendance: 90, venue_requirements: "Bigger" })]} eventStatus="Planning" />);

  expect(screen.getByText("Accept some of these changes")).toBeDefined();
});

// AC20-N4 (negative, hotfix 20): a one-field request has nothing to split
test("does not offer a partial decision for a single field", () => {
  render(<ChangeRequestPanel requests={[pending({ expected_attendance: 90 })]} eventStatus="Planning" />);

  expect(screen.queryByText("Accept some of these changes")).toBeNull();
});

// AC20-H3 (happy, hotfix 20): the form lists every field with a checkbox ticked by default
test("lists each field to accept or refuse", () => {
  render(<PartialChangeForm eventRequestId="e1" changeRequestId="c1" fields={FIELDS} />);

  expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  for (const box of screen.getAllByRole("checkbox")) expect((box as HTMLInputElement).checked).toBe(true);
  expect(screen.getByLabelText("Note to the Organiser (optional)")).toBeDefined();
});

// AC20-H4 (happy, hotfix 20): the Organiser sees what was refused and why
test("shows the refused changes of a partly approved request", () => {
  render(
    <RefusedChanges request={{
      status: "Partially Approved",
      rejected_changes: { venue_requirements: { value: "A bigger room", reason: "None free" } },
    }} />,
  );

  expect(screen.getByText("Not accepted")).toBeDefined();
  expect(screen.getByText(/A bigger room/)).toBeDefined();
  expect(screen.getByText(/Reason: None free/)).toBeDefined();
});

// AC20-N5 (negative, hotfix 20): nothing is shown for a request that was not partly refused
test.each(["Approved", "Rejected", "Pending"] as const)("shows no refusals for a %s request", (status) => {
  const { container } = render(<RefusedChanges request={{ status, rejected_changes: null }} />);

  expect(container.textContent).toBe("");
});

// AC20-H5 (happy, hotfix 20): the Organiser's notice says how many changes were applied and the reasons
test("describes a partly approved notice", () => {
  const notice: AppNotification = {
    id: "n1", event_type: "event_change_partly_approved", read_at: null, created_at: "2030-01-01T00:00:00Z",
    payload: {
      event_request_id: "e1",
      accepted_fields: ["expected_attendance"],
      refused: { venue_requirements: "None free" },
    },
  };

  const summary = describeNotification(notice);

  expect(summary.message).toBe("Your event change request was partly approved: 1 change was applied and 1 was not.");
  expect(summary.detail).toBe("Venue requirements: None free");
  expect(summary.href).toBe("/event-requests/e1/edit");
});

// AC21-H1 (happy, hotfix 21): a withdrawn request is its own, distinguishable status
test("shows a withdrawn request as withdrawn, not cancelled or rejected", () => {
  render(<StatusProgress status="Withdrawn" />);

  expect(screen.getByText("Withdrawn")).toBeDefined();
  expect(screen.getByText(/withdrawn at the organiser's request/)).toBeDefined();
  expect(screen.getByText(/ended as withdrawn/)).toBeDefined();
});

// AC21-H2 (happy, hotfix 21): the Organiser's notice names the event
test("describes a withdrawal notice", () => {
  const summary = describeNotification({
    id: "n", event_type: "event_request_withdrawn", read_at: null, created_at: "x",
    payload: { event_request_id: "e1", event_name: "Gala" },
  });

  expect(summary.message).toBe("Gala was withdrawn, as you asked.");
});

// AC22-H1 (happy, hotfix 22): a postponed event explains that planning starts again
test("shows a postponed event with its explanation", () => {
  render(<StatusProgress status="Postponed" />);

  expect(screen.getByText(/bookings were released and a new date will be set/)).toBeDefined();
  expect(screen.getByText(/Planning and confirmation start again/)).toBeDefined();
});

// AC22-H2 (happy, hotfix 22): the postpone form asks for a reason; the resume form for a date
test("renders the postpone and resume forms", () => {
  const { unmount } = render(<PostponeEventForm eventRequestId="e1" />);
  expect(screen.getByLabelText("Reason")).toBeDefined();
  expect(screen.getByRole("button", { name: "Postpone event" })).toBeDefined();
  unmount();

  render(<ResumeEventForm eventRequestId="e1" />);
  expect(screen.getByLabelText("New date and time (Singapore time)")).toBeDefined();
  expect(screen.getByRole("button", { name: "Set new date" })).toBeDefined();
});

// AC22-H3 (happy, hotfix 22): submitting the postpone form calls its action with the reason
test("submits the postponement reason", async () => {
  actions.postpone.mockResolvedValue({ saved: true });
  render(<PostponeEventForm eventRequestId="e1" />);

  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Venue closed" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Postpone event" })); });

  expect(actions.postpone).toHaveBeenCalledTimes(1);
  expect(actions.postpone.mock.calls[0][0]).toBe("e1");
  expect((actions.postpone.mock.calls[0][2] as FormData).get("reason")).toBe("Venue closed");
  await waitFor(() => expect(screen.getByText("The event is postponed.")).toBeDefined());
});

// AC22-N1 (negative, hotfix 22): a refusal from the action is shown
test("shows why a postponement was refused", async () => {
  actions.postpone.mockResolvedValue({ message: "This event can't be postponed from its current status." });
  render(<PostponeEventForm eventRequestId="e1" />);

  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "x" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Postpone event" })); });

  expect((await screen.findByRole("alert")).textContent).toMatch(/can't be postponed/);
});

// AC22-H4 (happy, hotfix 22): who is told, and what the notices say
test.each([
  ["event_postponed", ["event_organiser"], { reason: "Venue closed" }, "Gala has been postponed. A new date will be announced.", "/event-requests/e1/edit", "Venue closed"],
  ["event_postponed", ["attendee"], {}, "Gala has been postponed. A new date will be announced.", "/events/e1", undefined],
  ["event_postponed", ["venue_staff"], {}, "Gala has been postponed. A new date will be announced.", null, undefined],
  ["event_resumed", ["attendee"], { proposed_date_times: ["2030-03-04T01:30:00Z"] }, "Gala has a new date.", "/events/e1", "4 Mar 2030, 9:30 am"],
])("describes a %s notice for %j", (type, roles, extra, message, href, detail) => {
  const summary = describeNotification({
    id: "n", event_type: type, read_at: null, created_at: "x",
    payload: { event_request_id: "e1", event_name: "Gala", ...extra },
  }, roles);

  expect(summary.message).toBe(message);
  expect(summary.href).toBe(href);
  expect(summary.detail).toBe(detail);
});

// AC23-H1, AC23-B1, AC23-B2, AC23-N1 (hotfix 23): VIP places are what is left of the venue once normal registration is full
test.each([
  [{ registered: 100, registration_capacity: 100, venue_capacity: 120 }, 20],
  [{ registered: 119, registration_capacity: 100, venue_capacity: 120 }, 1],
  [{ registered: 120, registration_capacity: 100, venue_capacity: 120 }, 0],
  [{ registered: 99, registration_capacity: 100, venue_capacity: 120 }, 0],
  [{ registered: 100, registration_capacity: 100, venue_capacity: null }, 0],
  [{ registered: 0, registration_capacity: null, venue_capacity: 120 }, 0],
])("counts VIP places for %j", (info, expected) => {
  expect(vipPlaces(info)).toBe(expected);
});

// AC23-H2 (happy, hotfix 23): the add-attendee form tells the Coordinator about the VIP places
test("tells the coordinator how many VIPs can still be added", () => {
  render(<ManualRegistrationForm eventRequestId="e1" vipPlaces={20} />);

  expect(screen.getByText(/Normal registration is full\. You can still add 20 more people/)).toBeDefined();
});

// AC23-N2 (negative, hotfix 23): no hint while there is still normal room, or none above it
test.each([0, undefined])("shows no VIP hint for %s", (places) => {
  render(<ManualRegistrationForm eventRequestId="e1" vipPlaces={places} />);

  expect(screen.queryByText(/Normal registration is full/)).toBeNull();
});

// AC24-H1 (happy, hotfix 24): the form asks for the new organiser's email and a reason
test("renders the change organiser form", () => {
  render(<ChangeOrganiserForm eventRequestId="e1" />);

  expect(screen.getByLabelText("New organiser's email")).toBeDefined();
  expect(screen.getByLabelText("Reason")).toBeDefined();
  expect(screen.getByRole("button", { name: "Change organiser" })).toBeDefined();
});

// AC24-H2 (happy, hotfix 24): both people are told, differently
test.each([
  [true, "You are now the Event Organiser for Gala.", "/event-requests/e1/edit"],
  [false, "You are no longer the Event Organiser for Gala. A coordinator handed it to someone else.", null],
])("describes the organiser change notice (became organiser: %s)", (became, message, href) => {
  const summary = describeNotification({
    id: "n", event_type: "event_organiser_changed", read_at: null, created_at: "x",
    payload: { event_request_id: "e1", event_name: "Gala", became_organiser: became },
  });

  expect(summary.message).toBe(message);
  expect(summary.href).toBe(href);
});

// AC25-H1 (happy, hotfix 25): an essential requirement offers "not essential" with a note
test("offers to mark an essential requirement not essential", () => {
  render(<EssentialForm eventRequestId="e1" requirementId="r1" essential />);

  expect(screen.getByLabelText(/what was agreed with Technical Support/)).toBeDefined();
  expect(screen.getByRole("button", { name: "Mark not essential" })).toBeDefined();
  expect((document.querySelector('input[name="essential"]') as HTMLInputElement).value).toBe("false");
});

// AC25-H2 (happy, hotfix 25): a not-essential requirement offers to put it back, with no note
test("offers to mark a not-essential requirement essential again", () => {
  render(<EssentialForm eventRequestId="e1" requirementId="r1" essential={false} />);

  expect(screen.queryByLabelText(/what was agreed/)).toBeNull();
  expect(screen.getByRole("button", { name: "Mark essential again" })).toBeDefined();
  expect((document.querySelector('input[name="essential"]') as HTMLInputElement).value).toBe("true");
});

// AC25-H3 (happy, hotfix 25): submitting passes the requirement and the note to the action
test("submits the not-essential note", async () => {
  actions.essential.mockResolvedValue({ saved: true });
  render(<EssentialForm eventRequestId="e1" requirementId="r1" essential />);

  fireEvent.change(screen.getByLabelText(/what was agreed/), { target: { value: "Support brings one" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Mark not essential" })); });

  const call = actions.essential.mock.calls[0];
  expect(call.slice(0, 2)).toEqual(["e1", "r1"]);
  expect((call[3] as FormData).get("note")).toBe("Support brings one");
});

// AC25-N1 (negative, hotfix 25): a refusal is shown beside the requirement
test("shows why marking a requirement failed", async () => {
  actions.essential.mockResolvedValue({ message: "This event is closed, so its requirements can't be changed." });
  render(<EssentialForm eventRequestId="e1" requirementId="r1" essential />);

  fireEvent.change(screen.getByLabelText(/what was agreed/), { target: { value: "x" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Mark not essential" })); });

  expect(within(await screen.findByRole("alert")).getByText(/event is closed/)).toBeDefined();
});
