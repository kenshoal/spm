import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

// SCRUM-19 increment-2 review fixes: one failed candidate load stays inside its
// requirement (AC4-X1: a failed load is an error, never an empty list, and never
// the whole request page), and a recorded requirement clears the form so a
// second click cannot record a duplicate (AC1-H1 (F)).

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

import { TechnicalSupportPanel } from "@/app/coordination/requests/[id]/technical-support-panel";
import { RequirementForm } from "@/app/coordination/requests/[id]/requirement-form";
import type { TechnicalSupportRequirement } from "@/lib/technical-support";

afterEach(cleanup);
beforeEach(() => {
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
const REQ_IT = "aaaa0000-0000-4000-8000-000000000002";

function requirement(overrides: Partial<TechnicalSupportRequirement>): TechnicalSupportRequirement {
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

// AC4-X1 (cross-cutting): a candidates outage on one requirement shows an
// alert on that requirement only; the panel and the other requirement still
// render, and the failed one offers no Assign button or misleading empty state.
test("a failed candidate load is an alert on that requirement, not a page crash", async () => {
  data.support.mockResolvedValue([
    requirement({}),
    requirement({ id: REQ_IT, skill_tag: "it_network", description: "Venue Wi-Fi for 300 delegates" }),
  ]);
  data.staff.mockResolvedValue([{ id: "tss-av", email: "technical_support@example.com" }]);
  data.candidates.mockImplementation((_event: string, rid: string) =>
    rid === REQ_AV
      ? Promise.reject(new Error("candidates failed with status 500"))
      : Promise.resolve([{ staff_id: "tss-av", already_assigned: false }]),
  );

  render(await TechnicalSupportPanel({ eventRequestId: EVENT_ID, status: "Planning" }));

  const [av, it] = screen.getAllByRole("article");
  expect(within(av).getByRole("alert").textContent).toBe(
    "Suitable staff could not be loaded. Refresh to try again.",
  );
  expect(within(av).queryByRole("button", { name: "Assign" })).toBeNull();
  expect(within(av).queryByText(/No suitable Technical Support Staff/)).toBeNull();
  expect(within(it).getByRole("button", { name: "Assign" })).toBeDefined();
  expect(within(it).queryByRole("alert")).toBeNull();
});

// AC1-H1 (F): after a requirement is recorded the description, counter and
// skill reset, so the submit is disabled again and cannot record a duplicate.
test("a recorded requirement clears the form", async () => {
  actions.recordSupportRequirement.mockResolvedValue({});
  render(<RequirementForm eventRequestId={EVENT_ID} />);

  const textarea = screen.getByLabelText("What support is needed?") as HTMLTextAreaElement;
  const select = screen.getByLabelText("Skill") as HTMLSelectElement;
  fireEvent.change(textarea, { target: { value: "Venue Wi-Fi for 300 delegates" } });
  fireEvent.change(select, { target: { value: "it_network" } });
  const button = screen.getByRole("button", { name: "Record requirement" }) as HTMLButtonElement;
  expect(button.disabled).toBe(false);

  await act(async () => {
    fireEvent.click(button);
  });

  await vi.waitFor(() => expect(textarea.value).toBe(""));
  expect(actions.recordSupportRequirement).toHaveBeenCalledTimes(1);
  expect(select.value).toBe("");
  expect(screen.getByText("0/2000")).toBeDefined();
  expect(
    (screen.getByRole("button", { name: "Record requirement" }) as HTMLButtonElement).disabled,
  ).toBe(true);
});

// AC1-X3 (cross-cutting): a refused requirement keeps what was typed so the
// coordinator can correct it, and shows the message.
test("a refused requirement keeps the typed text", async () => {
  actions.recordSupportRequirement.mockResolvedValue({
    message: "Technical support can only be arranged for approved, planning or confirmed events",
  });
  render(<RequirementForm eventRequestId={EVENT_ID} />);

  const textarea = screen.getByLabelText("What support is needed?") as HTMLTextAreaElement;
  fireEvent.change(textarea, { target: { value: "Venue Wi-Fi for 300 delegates" } });
  fireEvent.change(screen.getByLabelText("Skill"), { target: { value: "it_network" } });

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Record requirement" }));
  });

  await vi.waitFor(() =>
    expect(screen.getByRole("alert").textContent).toBe(
      "Technical support can only be arranged for approved, planning or confirmed events",
    ),
  );
  expect(textarea.value).toBe("Venue Wi-Fi for 300 delegates");
});
