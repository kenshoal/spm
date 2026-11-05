import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// SCRUM-17 AC2-H1 (happy): the full decision loop — clarify, organiser response, resume, approve —
// keeps one request, its reasons and its statuses consistent across both roles
// (AC2, AC3 and AC4; the read-only field checks at each step also prove AC1).
// Purpose: Proves the full clarification loop keeps one request, its reason and its status consistent across both roles.
test("coordinator requests clarification, organiser responds and coordinator approves", async ({
  page,
  request,
}) => {
  const seeded = await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Under Review",
      organiser_id: "playwright-user",
      coordinator_id: "playwright-coordinator",
      event_name: "SCRUM-17 Review Workshop",
      purpose: "Exercise every event review field",
      description: "Unique description for the coordinator review.",
      proposed_date_times: ["2026-11-20T02:00:00Z"],
      expected_attendance: 40,
      venue_requirements: "Seminar room with movable seating",
      accessibility_needs: "Step-free entrance and accessible washroom",
      equipment_requirements: "Projector and presentation clicker",
      registration_needs: "Online registration with name badges",
    },
  });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  for (const value of [
    "SCRUM-17 Review Workshop",
    "Exercise every event review field",
    "Unique description for the coordinator review.",
    "40",
    "Seminar room with movable seating",
    "Step-free entrance and accessible washroom",
    "Projector and presentation clicker",
    "Online registration with name badges",
  ]) {
    await expect(page.getByText(value, { exact: true })).toBeVisible();
  }
  await expect(page.getByText(/20 Nov 2026/)).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /save draft|submit request|delete/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Request clarification" }).click();
  const decisionDialog = page.getByRole("dialog", {
    name: "Request clarification from the organiser",
  });
  await decisionDialog
    .getByRole("textbox")
    .fill("Clarify whether a microphone is required.");
  await decisionDialog.getByRole("button", { name: "Request clarification" }).click();
  await expect(page.getByText("Changes Requested", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Clarify whether a microphone is required.")).toBeVisible();

  await page.context().addCookies(sessionCookie("test-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(page.getByText(/submitted request remains read-only/i).first()).toBeVisible();
  await expect(page.getByText("Clarify whether a microphone is required.")).toBeVisible();
  await expect(page.getByText("Projector and presentation clicker", { exact: true })).toBeVisible();
  await page.getByLabel("Clarification response").fill("A wireless microphone is required.");
  await page.getByRole("button", { name: "Send clarification response" }).click();
  await expect(page.getByText(/response was sent/i)).toBeVisible();

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  await expect(page.getByText("A wireless microphone is required.")).toBeVisible();
  await expect(page.getByText("Projector and presentation clicker", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Continue review" }).click();
  await page.getByRole("button", { name: "Approve request" }).click();
  const approveDialog = page.getByRole("dialog", {
    name: "Approve this request?",
  });
  await approveDialog.getByRole("button", { name: "Approve request" }).click();
  await expect(page.getByText("Approved", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Review activity" })).toBeVisible();
  await expect(page.getByText("Changes Requested", { exact: true })).toBeVisible();
  await expect(page.getByText("Clarify whether a microphone is required.")).toBeVisible();
  await expect(page.getByText("A wireless microphone is required.")).toBeVisible();
});

// SCRUM-17 AC3-X2 (cross-cutting): a failed history read shows an accessible alert and
// withholds the decision, resume and response controls for both actors.
// Purpose: A failed history read blocks blind clarification actions for both actors.
test("shows review activity failures and withholds dependent actions", async ({
  page,
  request,
}) => {
  const coordinatorSeed = await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Under Review",
      organiser_id: "playwright-user",
      coordinator_id: "playwright-coordinator",
      event_name: "Unavailable coordinator history",
      review_history_unavailable: true,
    },
  });
  const coordinatorEvent = await coordinatorSeed.json();

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${coordinatorEvent.id}`);
  await expect(page.getByRole("alert", { name: "Review activity unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve request" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Request clarification" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reject request" })).toHaveCount(0);

  const respondedSeed = await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Changes Requested",
      organiser_id: "playwright-user",
      coordinator_id: "playwright-coordinator",
      event_name: "Unavailable responded history",
      review_history_unavailable: true,
      review_decision: {
        decision_status: "Changes Requested",
        reason: "Clarify the technical setup.",
        organiser_response: "A projector is required.",
        responded_at: "2026-09-30T02:00:00Z",
      },
    },
  });
  const respondedEvent = await respondedSeed.json();

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${respondedEvent.id}`);
  await expect(page.getByRole("alert", { name: "Review activity unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue review" })).toHaveCount(0);

  await page.context().addCookies(sessionCookie("test-session"));
  await page.goto(`/event-requests/${respondedEvent.id}/edit`);
  await expect(page.getByRole("alert", { name: "Review activity unavailable" })).toBeVisible();
  await expect(page.getByLabel("Clarification response")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send clarification response" })).toHaveCount(0);
});
