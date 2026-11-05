import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { EventRequestForm } from "@/app/event-requests/new/event-request-form";
import { RequestList } from "@/app/event-requests/request-list";
import { RequestTabs } from "@/app/event-requests/request-tabs";
import type { EventRequest } from "@/lib/event-requests";

afterEach(cleanup);

const draft: EventRequest = {
  id: "draft-1",
  organiser_id: "organiser-1",
  status: "Draft",
  event_name: "Technology Workshop",
  purpose: "Teach practical skills",
  description: null,
  proposed_date_times: [],
  expected_attendance: null,
  venue_requirements: null,
  accessibility_needs: null,
  equipment_requirements: null,
  registration_needs: null,
  created_at: "2026-09-13T03:00:00Z",
  updated_at: "2026-09-14T03:00:00Z",
};

const completeDraft: EventRequest = {
  ...draft,
  description: "A hands-on community programme",
  proposed_date_times: ["2026-10-20T02:00:00Z"],
  expected_attendance: 80,
  venue_requirements: "Classroom",
  accessibility_needs: "None",
  equipment_requirements: "Projector",
  registration_needs: "Online registration",
};

// SCRUM-8 AC3-P2 (partition): the list links a saved draft straight back to its
// edit form.
test("routes a saved draft to the editable form", () => {
  render(<RequestList requests={[draft]} />);

  expect(screen.getByRole("heading", { name: "Technology Workshop" })).toBeDefined();
  expect(
    screen.getByRole("link", { name: /continue draft/i }).getAttribute("href"),
  ).toBe("/event-requests/draft-1/edit");
});

// Purpose: Protects an organiser from losing an unfinished request through an accidental click.
test("requires confirmation before deleting a draft", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<RequestList requests={[draft]} />);

  fireEvent.click(screen.getByRole("button", { name: "Delete draft" }));

  const dialog = screen.getByRole("alertdialog", {
    name: "Delete event draft?",
  });
  expect(dialog.textContent).toContain("Technology Workshop");
  expect(fetchMock).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});

// SCRUM-8 AC2-P3 (partition): Save draft bypasses form validation so every
// field may stay empty on an early draft.
test("allows an incomplete event request to be saved as a draft", () => {
  render(<EventRequestForm />);

  const saveButton = screen.getByRole("button", { name: "Save draft" });
  expect((saveButton as HTMLButtonElement).formNoValidate).toBe(true);
  expect((screen.getByLabelText("Event name") as HTMLInputElement).required).toBe(true);
  expect(screen.getByRole("button", { name: "Submit request" })).toBeDefined();
});

// SCRUM-8 AC3-P1 (partition): reopening a draft restores its saved values for
// further editing.
test("prefills the form when an organiser continues a draft", () => {
  render(<EventRequestForm request={draft} />);

  expect((screen.getByLabelText("Event name") as HTMLInputElement).value).toBe(
    "Technology Workshop",
  );
  expect((screen.getByLabelText("Purpose") as HTMLTextAreaElement).value).toBe(
    "Teach practical skills",
  );
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDefined();
});

// SCRUM-11 AC7-X1 (cross-cutting): submission demands explicit confirmation
// that the request becomes read-only.
test("confirms submission of a complete request", () => {
  render(<EventRequestForm request={completeDraft} />);

  fireEvent.click(screen.getByRole("button", { name: "Submit request" }));

  const dialog = screen.getByRole("alertdialog", {
    name: "Submit event request?",
  });
  expect(dialog.textContent).toContain("cannot edit or delete");
});

// SCRUM-11 AC7-P1 (partition): a Submitted request keeps only the view control
// and loses its draft mutation controls.
test("renders a submitted request as read-only in the list", () => {
  render(<RequestList requests={[{ ...completeDraft, status: "Submitted" }]} />);

  expect(screen.getByText("Submitted")).toBeDefined();
  expect(screen.getByRole("link", { name: /view request/i })).toBeDefined();
  expect(screen.queryByRole("button", { name: "Delete draft" })).toBeNull();
});

// Purpose: Gives organisers visible request groupings and record counts for status tracking.
test("shows all request tracking tabs with counts", () => {
  render(
    <RequestTabs
      selected="submitted"
      counts={{ all: 3, draft: 1, submitted: 2, "in-progress": 1, completed: 0 }}
    />,
  );

  expect(screen.getByRole("link", { name: "All (3)" })).toBeDefined();
  expect(screen.getByRole("link", { name: "Draft (1)" })).toBeDefined();
  expect(screen.getByRole("link", { name: "Submitted (2)" }).getAttribute("aria-current")).toBe("page");
  expect(screen.getByRole("link", { name: "In Progress (1)" })).toBeDefined();
  expect(screen.getByRole("link", { name: "Completed (0)" })).toBeDefined();
});
