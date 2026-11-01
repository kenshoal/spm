import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const cookie = (value: string) => [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];

async function seed(request: import("@playwright/test").APIRequestContext, overrides: Record<string, unknown>) {
  const seeded = await request.post(`${EVENT_API}/__seed`, {
    data: {
      organiser_id: "playwright-change-request-owner",
      coordinator_id: "playwright-coordinator",
      purpose: "Customer ruling checks",
      description: "Seeded for the customer ruling hotfixes.",
      proposed_date_times: ["2036-11-20T02:00:00Z"],
      expected_attendance: 40,
      venue_requirements: "Seminar room",
      accessibility_needs: "Step-free access",
      equipment_requirements: "Projector",
      registration_needs: "Online registration",
      ...overrides,
    },
  });
  expect(seeded.status()).toBe(201);
  return seeded.json() as Promise<{ id: string; event_name: string }>;
}

// AC21-X1 (cross-cutting, hotfix 21): a Coordinator records a withdrawal; it stays distinguishable
test("coordinator records the withdrawal of a request under review", async ({ page, request }) => {
  const event = await seed(request, { status: "Under Review", event_name: "Hotfix 21 Withdrawn Forum" });
  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);

  await page.getByRole("button", { name: "Record withdrawal" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Record withdrawal" }).click();

  await expect(page.getByText("Withdrawn", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/no further actions are available/)).toBeVisible();
  const saved = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers: { Authorization: "Bearer coordinator-session" } });
  expect((await saved.json()).status).toBe("Withdrawn");
});

// AC22-X1 (cross-cutting, hotfix 22): postpone with no date, then give it a new date
test("coordinator postpones an event and later sets its new date", async ({ page, request }) => {
  const event = await seed(request, { status: "Planning", event_name: "Hotfix 22 Postponed Forum" });
  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);

  await page.getByText("Postpone this event", { exact: true }).click();
  const postponeForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Postpone event" }) });
  await postponeForm.getByLabel("Reason", { exact: true }).fill("The venue is closed that week");
  await postponeForm.getByRole("button", { name: "Postpone event" }).click();
  // The page refreshes into the postponed state, so the new-date form replaces the postpone form.
  await expect(page.getByRole("button", { name: "Set new date" })).toBeVisible();
  await expect(page.getByText("Postponed", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Postpone event" })).toHaveCount(0);

  await page.getByLabel("New date and time (Singapore time)").fill("2036-12-01T09:30");
  await page.getByRole("button", { name: "Set new date" }).click();
  await expect(page.getByRole("button", { name: "Set new date" })).toHaveCount(0);
  const saved = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers: { Authorization: "Bearer coordinator-session" } });
  expect(await saved.json()).toMatchObject({ status: "Planning", proposed_date_times: ["2036-12-01T09:30:00+08:00"] });
});

// AC24-X1 (cross-cutting, hotfix 24): the Coordinator hands the event to another Organiser
test("coordinator changes the event organiser and a bad email is explained", async ({ page, request }) => {
  const event = await seed(request, { status: "Planning", event_name: "Hotfix 24 Organiser Forum" });
  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);

  await page.getByText("Change the Event Organiser", { exact: true }).click();
  const organiserForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Change organiser" }) });
  await organiserForm.getByLabel("New organiser's email").fill("nobody@example.test");
  await organiserForm.getByLabel("Reason", { exact: true }).fill("Left the company");
  await organiserForm.getByRole("button", { name: "Change organiser" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "No Event Organiser account has that email address." })).toBeVisible();

  await organiserForm.getByLabel("New organiser's email").fill("new-organiser@example.test");
  await organiserForm.getByRole("button", { name: "Change organiser" }).click();
  await expect(page.getByText("The Event Organiser is changed.")).toBeVisible();
  const saved = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers: { Authorization: "Bearer coordinator-session" } });
  expect((await saved.json()).organiser_id).toBe("playwright-new-organiser");
});

// AC20-X1 (cross-cutting, hotfix 20): accept one change, refuse the others with reasons; the Organiser reads both
test("coordinator partly approves a change request and the organiser sees what was refused", async ({ page, request }) => {
  const event = await seed(request, { status: "Planning", event_name: "Hotfix 20 Partial Forum" });
  const created = await request.post(`${EVENT_API}/event-requests/${event.id}/change-requests`, {
    headers: { Authorization: "Bearer change-request-owner-session" },
    data: { explanation: "More people and a bigger room.", expected_attendance: 80, venue_requirements: "Large auditorium" },
  });
  expect(created.status()).toBe(201);

  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  const proposal = page.getByRole("article").filter({ hasText: "More people and a bigger room." });
  await proposal.getByText("Accept some of these changes").click();
  const venue = proposal.getByRole("group", { name: "Venue requirements" });
  await venue.getByLabel("Accept this change").uncheck();
  await proposal.getByRole("button", { name: "Apply the accepted changes" }).click();
  await expect(proposal.getByText("Give a reason for every field you do not accept.")).toBeVisible();
  await venue.getByLabel("Reason if not accepted").fill("No auditorium is free that day");
  await proposal.getByRole("button", { name: "Apply the accepted changes" }).click();

  await expect(proposal.getByText("Partially Approved", { exact: true })).toBeVisible();
  await expect(proposal.getByText("No auditorium is free that day")).toBeVisible();
  const saved = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers: { Authorization: "Bearer coordinator-session" } });
  expect(await saved.json()).toMatchObject({ expected_attendance: 80, venue_requirements: "Seminar room" });

  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  const history = page.getByRole("region", { name: "Change request history" });
  await expect(history.getByText("Partially Approved", { exact: true })).toBeVisible();
  await expect(history.getByText("Not accepted")).toBeVisible();
  await expect(history.getByText(/No auditorium is free that day/)).toBeVisible();
});
