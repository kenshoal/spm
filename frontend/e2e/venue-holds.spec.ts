import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const VENUE_API = "http://127.0.0.1:8105";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// Two days from now, as the Singapore wall-clock time a datetime-local field takes.
function singaporeInTwoDays(): string {
  const later = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000 + 8 * 60 * 60 * 1000);
  return later.toISOString().slice(0, 16);
}

// AC1-E1, AC5-E1, AC6-E1 (happy): SCRUM-18 end to end in a browser — a coordinator
// holds a venue for their event, sees it on the event page, as "Tentatively held"
// (with setup and turnaround) on the availability calendar and in venue search, then
// releases it and the time is free again. The mock venue API does not check the event's assignment, so
// this proves the screens, not the real service's access rule.
test("coordinator holds a venue, sees it held on the calendar, then releases it", async ({ page, request }) => {
  const stamp = Date.now();
  const event = await (await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Planning",
      organiser_id: "playwright-user",
      coordinator_id: "playwright-coordinator",
      event_name: `Hold Summit ${stamp}`,
      purpose: "Keep a room while planning",
      description: "A conference still being finalised.",
      proposed_date_times: ["2026-12-14T02:00:00Z"],
      expected_attendance: 80,
    },
  })).json();
  const venue = await (await request.post(`${VENUE_API}/__seed`, {
    data: { name: `Hold Hall ${stamp}`, location: `Wing H ${stamp}`, max_capacity: 120, setup_minutes: 30, turnaround_minutes: 45 },
  })).json();

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);

  const panel = page.getByRole("region", { name: "Venue holds" });
  await expect(panel).toContainText("No venue holds yet.");
  await panel.getByLabel("Venue").selectOption({ label: `Hold Hall ${stamp}` });
  await panel.getByLabel("Hold expires (Singapore time)").fill(singaporeInTwoDays());
  await panel.getByLabel("Start date").fill("2026-12-14");
  await panel.getByLabel("End date").fill("2026-12-14");
  await panel.getByLabel("Start time").selectOption("10:00");
  await panel.getByLabel("End time").selectOption("12:00");
  await panel.getByRole("button", { name: "Hold venue" }).click();

  const row = panel.getByRole("listitem").filter({ hasText: `Hold Hall ${stamp}` });
  await expect(row).toContainText("Held");
  await expect(row).toContainText("10:00–12:00");
  await expect(row.getByRole("button", { name: `Request booking for hold at Hold Hall ${stamp}` })).toBeVisible();

  await page.goto(`/venues/availability?venue=${venue.id}&month=2026-12`);
  await expect(page.getByText("Tentatively held 09:30–12:45")).toBeVisible();

  const search = `/venues/search?${new URLSearchParams({ location: `Wing H ${stamp}`, date: "2026-12-14", start_time: "11:00", end_time: "12:00" })}`;
  await page.goto(search);
  const result = page.getByRole("article", { name: `Hold Hall ${stamp}` });
  await expect(result).toContainText("Tentatively held");

  await page.goto(`/coordination/requests/${event.id}`);
  page.once("dialog", (dialog) => dialog.accept());
  await row.getByRole("button", { name: `Release hold at Hold Hall ${stamp}` }).click();
  await expect(row).toContainText("Released");
  await expect(row.getByRole("button")).toHaveCount(0);

  await page.goto(`/venues/availability?venue=${venue.id}&month=2026-12`);
  await expect(page.getByText("Tentatively held 09:30–12:45")).toHaveCount(0);

  await page.goto(search);
  await expect(result).toBeVisible();
  await expect(result).not.toContainText("Tentatively held");
});
