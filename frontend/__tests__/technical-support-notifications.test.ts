import { expect, test } from "vitest";

import { describeNotification, type AppNotification } from "@/lib/notifications";

function makeNotification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n1",
    event_type: "technical_support_assigned",
    payload: {
      event_request_id: "req-9",
      event_name: "Tech Summit 2030",
      requirement_id: "aaaa0000-0000-4000-8000-000000000001",
      skill_tag: "audio_visual",
      assigned_by: "coord-1",
    },
    read_at: null,
    created_at: "2026-10-21T03:15:00Z",
    ...overrides,
  };
}

// AC5-H4 (happy): the assigned staff member's notice names the skill and the
// event. There is no link — a TSS assignments page is out of scope, and the
// coordination request page is closed to technical_support.
test("describes a technical support assignment naming the skill and event", () => {
  expect(describeNotification(makeNotification())).toEqual({
    message: "You've been assigned as Audio-visual support for Tech Summit 2030.",
    href: null,
  });
});

// AC5-H4 (partition): each skill tag in the vocabulary names its label.
test.each(
  [
    ["AC5-H4a", "audio_visual", "Audio-visual"],
    ["AC5-H4b", "lighting", "Lighting"],
    ["AC5-H4c", "it_network", "IT and network"],
    ["AC5-H4d", "livestream", "Livestream"],
  ] as const,
)("renders each skill tag's label: %s", (_id, skillTag, label) => {
  const notification = makeNotification({ payload: { skill_tag: skillTag } });

  expect(describeNotification(notification).message).toBe(
    `You've been assigned as ${label} support.`,
  );
});

// AC5-H4 (negative): a payload without the event name still reads as a sentence.
test("still names the skill when the event name is missing", () => {
  const notification = makeNotification({
    payload: { event_request_id: "req-9", skill_tag: "lighting" },
  });

  const summary = describeNotification(notification);
  expect(summary.message).toBe("You've been assigned as Lighting support.");
  expect(summary.href).toBeNull();
});
