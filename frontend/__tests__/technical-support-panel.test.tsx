import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({
    id: "coord-1",
    email: "c@example.com",
    role: "event_coordinator",
    roles: ["event_coordinator"],
  }),
}));
const actions = vi.hoisted(() => ({
  recordSupportRequirement: vi.fn(),
  assignSupportStaff: vi.fn(),
}));
vi.mock("@/app/coordination/requests/[id]/technical-support-actions", () => ({
  recordSupportRequirement: actions.recordSupportRequirement,
  assignSupportStaff: actions.assignSupportStaff,
}));
const data = vi.hoisted(() => ({
  support: vi.fn(),
  staff: vi.fn(),
  candidates: vi.fn(),
}));
vi.mock("@/lib/technical-support", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/technical-support")>()),
  listEventTechnicalSupport: data.support,
  listTechnicalSupportStaff: data.staff,
  listCandidates: data.candidates,
}));

import {
  TechnicalSupportList,
  TechnicalSupportLoading,
  TechnicalSupportPanel,
} from "@/app/coordination/requests/[id]/technical-support-panel";
import { RequirementForm } from "@/app/coordination/requests/[id]/requirement-form";
import type {
  Candidate,
  StaffOption,
  TechnicalSupportRequirement,
} from "@/lib/technical-support";

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
  data.support.mockReset();
  data.staff.mockReset();
  data.candidates.mockReset();
  actions.recordSupportRequirement.mockReset();
  actions.assignSupportStaff.mockReset();
});

const EVENT_ID = "11111111-1111-4111-8111-111111111111";
const REQ_AV = "aaaa0000-0000-4000-8000-000000000001";
const REQ_LIVE = "aaaa0000-0000-4000-8000-000000000004";

function requirement(overrides: Partial<TechnicalSupportRequirement> = {}): TechnicalSupportRequirement {
  return {
    id: REQ_AV,
    event_request_id: EVENT_ID,
    description: "Two wireless mics and a mixing-desk operator for the keynote",
    skill_tag: "audio_visual",
    recorded_by: "coord-1",
    recorded_at: "2026-10-20T09:00:00Z",
    assigned_staff: [],
    ...overrides,
  };
}

const staff: StaffOption[] = [{ id: "tss-av", email: "technical_support@example.com" }];
const avCandidates: Candidate[] = [
  { staff_id: "tss-av", already_assigned: true },
  { staff_id: "tss-av2", already_assigned: false },
];

const assigned = requirement({
  assigned_staff: [
    { staff_id: "tss-av", assigned_by: "coord-1", assigned_at: "2026-10-21T02:30:00Z" },
  ],
});
const unlabelled = requirement({
  id: "aaaa0000-0000-4000-8000-000000000002",
  skill_tag: "lighting",
  description: "Follow spot for the closing panel",
  assigned_staff: [
    { staff_id: "ghost-id", assigned_by: "coord-1", assigned_at: "2026-10-21T02:30:00Z" },
  ],
});
const livestream = requirement({
  id: REQ_LIVE,
  skill_tag: "livestream",
  description: "Stream the keynote to the overflow room",
});

function listProps(requirements: TechnicalSupportRequirement[]) {
  return {
    requirements,
    staff,
    candidates: new Map<string, Candidate[]>([
      [REQ_AV, avCandidates],
      [REQ_LIVE, []],
    ]),
    eventRequestId: EVENT_ID,
  };
}

// AC4-H1 (happy): the panel loads the requirements and labels everything for
// the coordinator's page.
test("the panel loads requirements, staff labels and candidates", async () => {
  data.support.mockResolvedValue([assigned, livestream]);
  data.staff.mockResolvedValue(staff);
  data.candidates.mockImplementation((_event: string, rid: string) =>
    rid === REQ_LIVE ? Promise.resolve([]) : Promise.resolve(avCandidates),
  );

  render(await TechnicalSupportPanel({ eventRequestId: EVENT_ID, status: "Planning" }));

  expect(data.support).toHaveBeenCalledWith(EVENT_ID);
  expect(data.staff).toHaveBeenCalledWith();
  expect(screen.getByText("Two wireless mics and a mixing-desk operator for the keynote")).toBeDefined();
  expect(screen.getByText("technical_support@example.com")).toBeDefined();
  expect(screen.getByText("Recorded by coord-1")).toBeDefined();
});

// AC4-X1 (cross-cutting): assigned staff are labelled by email, an unknown id
// falls back to the id, and an unassigned requirement says so.
test("labels staff by email, falls back to the id, and marks empty requirements", () => {
  render(<TechnicalSupportList {...listProps([assigned, unlabelled])} />);

  expect(screen.getByText("technical_support@example.com")).toBeDefined();
  expect(screen.getByText("ghost-id")).toBeDefined();
  expect(screen.getByText("Nobody assigned yet")).toBeDefined();
});

// AC4-X1 (cross-cutting): a failed requirements load is an alert, never an
// empty list.
test("a failed load shows an alert, not an empty list", async () => {
  data.support.mockRejectedValue(new Error("down"));
  data.staff.mockResolvedValue([]);
  data.candidates.mockResolvedValue([]);

  render(await TechnicalSupportPanel({ eventRequestId: EVENT_ID, status: "Planning" }));

  expect(screen.getByRole("alert").textContent).toContain("could not be loaded");
  expect(screen.queryByText("Nobody assigned yet")).toBeNull();
});

// AC3-P6 (partition): nobody holds the tag — a clear empty state and no way
// to assign.
test("a tag nobody holds shows the empty-candidate state without an Assign button", () => {
  render(<TechnicalSupportList {...listProps([livestream])} />);

  expect(
    screen.getByText("No suitable Technical Support Staff hold the Livestream skill"),
  ).toBeDefined();
  expect(screen.queryByRole("button", { name: "Assign" })).toBeNull();
});

// AC3-P6 (partition): the only suitable person is already assigned — the same
// empty-select state, worded for that case.
test("everyone suitable being assigned shows the all-assigned state", () => {
  const onlyAssigned = new Map<string, Candidate[]>([
    [REQ_AV, [{ staff_id: "tss-av", already_assigned: true }]],
  ]);

  render(
    <TechnicalSupportList
      requirements={[assigned]}
      staff={staff}
      candidates={onlyAssigned}
      eventRequestId={EVENT_ID}
    />,
  );

  expect(screen.getByText("Everyone suitable is already assigned.")).toBeDefined();
  expect(screen.queryByRole("button", { name: "Assign" })).toBeNull();
});

// AC4-H1 (happy): the candidate select offers only the staff who are not yet
// on the requirement, labelled by email with the id fallback.
test("the candidate select excludes staff who are already assigned", () => {
  render(<TechnicalSupportList {...listProps([assigned])} />);

  const select = screen.getByRole("combobox", { name: "Technical Support Staff" });
  const options = within(select).getAllByRole("option");
  expect(options.map((option) => option.textContent)).toEqual(["tss-av2"]);
});

// AC2-X6 (cross-cutting): a refused assignment shows the mapped message and
// leaves the assigned list unchanged.
test("a refused assignment explains itself and keeps the list", async () => {
  actions.assignSupportStaff.mockResolvedValue({
    message: "Already assigned to this requirement",
  });

  render(<TechnicalSupportList {...listProps([assigned])} />);

  const select = screen.getByRole("combobox", { name: "Technical Support Staff" });
  fireEvent.change(select, { target: { value: "tss-av" } });
  fireEvent.click(screen.getByRole("button", { name: "Assign" }));

  await vi.waitFor(() =>
    expect(screen.getByRole("alert").textContent).toBe(
      "Already assigned to this requirement",
    ),
  );
  expect(screen.getByText("technical_support@example.com")).toBeDefined();
  expect(actions.assignSupportStaff).toHaveBeenCalledWith(
    {},
    expect.any(FormData),
  );
});

// AC1-X3 (cross-cutting): the form blocks a blank description and offers
// exactly the four skill tags.
test("the requirement form blocks a blank description", () => {
  render(<RequirementForm eventRequestId={EVENT_ID} />);

  const button = screen.getByRole("button", { name: "Record requirement" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("Describe the support needed")).toBeDefined();
});

// AC1-X3 (cross-cutting): one character over the limit flips the counter into
// its error style.
test("the counter shows 2001/2000 in its error style", () => {
  render(<RequirementForm eventRequestId={EVENT_ID} />);

  fireEvent.change(screen.getByLabelText("What support is needed?"), {
    target: { value: "x".repeat(2001) },
  });

  const counter = screen.getByText("2001/2000");
  expect(counter.dataset.error).toBe("true");
  expect((screen.getByRole("button", { name: "Record requirement" }) as HTMLButtonElement).disabled).toBe(true);
});

// AC1-X3 (cross-cutting): the tag select offers exactly the four fixed labels
// in order.
test("the tag select offers exactly the four skill labels", () => {
  render(<RequirementForm eventRequestId={EVENT_ID} />);

  const select = screen.getByRole("combobox", { name: "Skill" });
  expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
    "Select a skill",
    "Audio-visual",
    "Lighting",
    "IT and network",
    "Livestream",
  ]);
});

// AC4-X1 (cross-cutting): the panel reserves its layout while loading.
test("the loading fallback is announced", () => {
  render(<TechnicalSupportLoading />);

  expect(screen.getByRole("status", { name: "Loading technical support" })).toBeDefined();
});
