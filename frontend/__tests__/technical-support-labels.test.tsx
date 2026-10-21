import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// SCRUM-19 increment-2 review follow-ups (UI): people are named, not shown as
// raw ids (AC4-H1 "who, assigned by"), and the description limit is counted
// the way the API and database count it (AC1-B*: trimmed, characters not
// UTF-16 units).

vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/app/coordination/requests/[id]/technical-support-actions", () => ({
  recordSupportRequirement: vi.fn(),
  assignSupportStaff: vi.fn(),
}));

import { TechnicalSupportList } from "@/app/coordination/requests/[id]/technical-support-panel";
import { RequirementForm } from "@/app/coordination/requests/[id]/requirement-form";
import type { Candidate, TechnicalSupportRequirement } from "@/lib/technical-support-options";

afterEach(cleanup);

const EVENT_ID = "11111111-1111-4111-8111-111111111111";

function requirement(overrides: Partial<TechnicalSupportRequirement>): TechnicalSupportRequirement {
  return {
    id: "aaaa0000-0000-4000-8000-000000000001",
    event_request_id: EVENT_ID,
    description: "Two wireless mics and a mixing-desk operator for the keynote",
    skill_tag: "audio_visual",
    recorded_by: "coord-1",
    recorded_at: "2026-10-20T09:00:00Z",
    assigned_staff: [],
    ...overrides,
  };
}

// AC4-H1 (F): the signed-in coordinator's own id reads as "you"; anyone else
// keeps the id fallback rather than an invented name.
test("the signed-in coordinator is named 'you', not by id", () => {
  render(
    <TechnicalSupportList
      requirements={[
        requirement({
          assigned_staff: [
            { staff_id: "tss-av", assigned_by: "coord-1", assigned_at: "2026-10-21T02:30:00Z" },
          ],
        }),
        requirement({
          id: "aaaa0000-0000-4000-8000-000000000002",
          skill_tag: "lighting",
          recorded_by: "coord-previous",
        }),
      ]}
      staff={[{ id: "tss-av", email: "technical_support@example.com" }]}
      candidates={new Map<string, Candidate[]>()}
      eventRequestId={EVENT_ID}
      currentUserId="coord-1"
    />,
  );

  const [mine, previous] = screen.getAllByRole("article");
  expect(within(mine).getByText("Recorded by you")).toBeDefined();
  expect(within(mine).getByText(/assigned by you/)).toBeDefined();
  expect(within(mine).queryByText(/coord-1/)).toBeNull();
  expect(within(previous).getByText("Recorded by coord-previous")).toBeDefined();
});

// AC1-B* (boundary): surrounding whitespace is trimmed before it is counted,
// as the action and the API do, so 2000 characters plus padding is allowed.
test("the counter and the submit ignore surrounding whitespace", () => {
  render(<RequirementForm eventRequestId={EVENT_ID} />);
  fireEvent.change(screen.getByLabelText("What support is needed?"), {
    target: { value: `  ${"x".repeat(2000)}\n` },
  });
  fireEvent.change(screen.getByLabelText("Skill"), { target: { value: "lighting" } });

  const counter = screen.getByText("2000/2000");
  expect(counter.getAttribute("data-error")).toBeNull();
  expect(
    (screen.getByRole("button", { name: "Record requirement" }) as HTMLButtonElement).disabled,
  ).toBe(false);
});

// AC1-B* (boundary): an emoji is one character to Postgres char_length and to
// Python len, so 2000 emoji are allowed and 2001 are not.
test("the counter counts characters, not UTF-16 units", () => {
  render(<RequirementForm eventRequestId={EVENT_ID} />);
  const textarea = screen.getByLabelText("What support is needed?");
  fireEvent.change(screen.getByLabelText("Skill"), { target: { value: "lighting" } });
  const button = () =>
    screen.getByRole("button", { name: "Record requirement" }) as HTMLButtonElement;

  fireEvent.change(textarea, { target: { value: "🎤".repeat(2000) } });
  expect(screen.getByText("2000/2000").getAttribute("data-error")).toBeNull();
  expect(button().disabled).toBe(false);

  fireEvent.change(textarea, { target: { value: "🎤".repeat(2001) } });
  expect(screen.getByText("2001/2000").getAttribute("data-error")).toBe("true");
  expect(button().disabled).toBe(true);
});
