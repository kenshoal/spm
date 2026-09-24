import { expect, test, type Page } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// Scope clicks to this request's card: specs share one mock API and run in
// parallel, so other requests (e.g. from home.spec.ts) can appear in the list.
function funRunCard(page: Page) {
  return page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: "Anniversary Fun Run" }) });
}

test.describe.serial("SCRUM-28 status tracking", () => {
  let eventId: string;

  // Purpose: Covers the critical handoff journey — an organiser-submitted
  // request becomes visible to the assigned coordinator, who starts review;
  // the organiser sees the tracked status; an unrelated coordinator sees
  // nothing (empty queue and not-found on the direct URL).
  test("organiser submits, assigned coordinator starts review, others see nothing", async ({
    page,
    request,
  }) => {
    await page.context().addCookies(sessionCookie("test-session"));
    await page.goto("/event-requests/new");
    await page.getByLabel("Event name").fill("Anniversary Fun Run");
    await page.getByLabel("Purpose").fill("Celebrate the club's tenth year");
    await page
      .getByLabel("Description")
      .fill("A 5km run followed by a community breakfast.");
    await page.getByLabel("Proposed date and time 1").fill("2026-11-14T08:00");
    await page.getByLabel("Expected attendance").fill("150");
    await page.getByLabel("Venue requirements").fill("Park loop and start line area");
    await page.getByLabel("Equipment requirements").fill("Water stations and flags");
    await page.getByLabel("Accessibility needs").fill("Wheelchair-accessible path");
    await page
      .getByLabel("Registration needs")
      .fill("Online sign-up with race pack collection");
    await page.getByRole("button", { name: "Submit request" }).click();
    const submitDialog = page.getByRole("alertdialog", {
      name: "Submit event request?",
    });
    await expect(submitDialog).toBeVisible();
    await submitDialog.getByRole("button", { name: "Submit request" }).click();
    await expect(page).toHaveURL(/\/event-requests\?status=submitted$/);

    const own = await (
      await request.get(`${EVENT_API}/event-requests`, {
        headers: { authorization: "Bearer test-session" },
      })
    ).json();
    eventId = own.find(
      (item: { event_name: string }) => item.event_name === "Anniversary Fun Run",
    ).id;
    expect(eventId).toBeDefined();

    // Boundary: no Ops Manager frontend exists on this branch (SCRUM-14 is
    // API-only), so the assignment step is driven through the API the way
    // the real ops workspace will.
    const assigned = await request.post(
      `${EVENT_API}/event-requests/${eventId}/coordinator`,
      {
        headers: { authorization: "Bearer ops-session" },
        data: { coordinator_id: "playwright-coordinator" },
      },
    );
    expect(assigned.status()).toBe(201);

    // Assignment alone must not move the status out of Submitted.
    await page.goto(`/event-requests/${eventId}/edit`);
    await expect(page.getByText(/coordinator has been assigned/i)).toBeVisible();
    await expect(page.locator('[aria-current="step"]')).toContainText("Submitted");

    await page.goto("/event-requests?status=in-progress");
    await expect(
      page.getByText("Requests being coordinated will appear here."),
    ).toBeVisible();

    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto("/coordination/requests");
    await expect(
      page.getByRole("heading", { name: "Requests assigned to you" }),
    ).toBeVisible();
    await expect(page.getByText("Anniversary Fun Run")).toBeVisible();
    await funRunCard(page).getByRole("link", { name: /open request/i }).click();
    await expect(
      page.getByRole("heading", { name: "Anniversary Fun Run" }),
    ).toBeVisible();
    await expect(page.getByText(/coordinator has been assigned/i)).toBeVisible();
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(
      page
        .getByRole("region", { name: "Status progress" })
        .getByText("Under Review", { exact: true })
        .first(),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Start review" })).toHaveCount(0);

    await page.context().addCookies(sessionCookie("test-session"));
    await page.goto("/event-requests?status=in-progress");
    await expect(page.getByText("Anniversary Fun Run")).toBeVisible();
    await funRunCard(page).getByRole("link", { name: /view request/i }).click();
    await expect(page.locator('[aria-current="step"]')).toContainText(
      "Under Review",
    );

    await page.context().addCookies(sessionCookie("other-coordinator-session"));
    await page.goto("/coordination/requests");
    await expect(page.getByText("No assigned requests")).toBeVisible();
    await page.goto(`/coordination/requests/${eventId}`);
    await expect(page.getByText("Request not found")).toBeVisible();
  });

  // Purpose: Covers the coordinator transitions — cancelling an in-flight
  // request closes it everywhere, and completing a confirmed event files it
  // under Completed for the organiser.
  test("coordinator cancels an in-flight request and completes a confirmed one", async ({
    page,
    request,
  }) => {
    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto(`/coordination/requests/${eventId}`);
    await page.getByRole("button", { name: "Cancel event" }).click();
    const cancelDialog = page.getByRole("alertdialog", {
      name: "Cancel this event?",
    });
    await expect(cancelDialog).toBeVisible();
    await cancelDialog.getByRole("button", { name: "Cancel event" }).click();
    await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
    await expect(
      page.getByText(/no further actions are available/i),
    ).toBeVisible();

    await page.context().addCookies(sessionCookie("test-session"));
    await page.goto("/event-requests?status=in-progress");
    await expect(page.getByText("Anniversary Fun Run")).toHaveCount(0);
    await page.goto("/event-requests");
    await expect(page.getByText("Anniversary Fun Run")).toBeVisible();

    // Boundary: Confirmed is written by the venue/ops stories that are not
    // implemented on this branch, so the seed hook stands in for them.
    const seed = await request.post(`${EVENT_API}/__seed`, {
      data: {
        status: "Confirmed",
        event_name: "Confirmed Charity Gala",
        purpose: "Annual fundraiser",
        organiser_id: "playwright-user",
        coordinator_id: "playwright-coordinator",
      },
    });
    expect(seed.status()).toBe(201);
    const gala = await seed.json();

    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto(`/coordination/requests/${gala.id}`);
    await expect(page.getByRole("button", { name: "Mark complete" })).toBeVisible();
    await page.getByRole("button", { name: "Mark complete" }).click();
    const completeDialog = page.getByRole("alertdialog", {
      name: "Mark this event complete?",
    });
    await expect(completeDialog).toBeVisible();
    await completeDialog.getByRole("button", { name: "Mark complete" }).click();
    await expect(
      page
        .getByRole("region", { name: "Status progress" })
        .getByText("Completed", { exact: true })
        .first(),
    ).toBeVisible();

    await page.context().addCookies(sessionCookie("test-session"));
    await page.goto("/event-requests?status=completed");
    await expect(page.getByText("Confirmed Charity Gala")).toBeVisible();
  });
});
