import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { EventRequestForm } from "@/app/event-requests/new/event-request-form";
import { RequestList } from "@/app/event-requests/request-list";
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

// Purpose: Confirms a saved draft gives the organiser a direct path back to editing it.
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

// Purpose: Proves every event-request field may remain empty when saving an early draft.
test("allows an incomplete event request to be saved as a draft", () => {
  render(<EventRequestForm />);

  const saveButton = screen.getByRole("button", { name: "Save draft" });
  expect((saveButton as HTMLButtonElement).formNoValidate).toBe(true);
  expect((screen.getByLabelText("Event name") as HTMLInputElement).required).toBe(false);
  expect(screen.queryByRole("button", { name: /submit for review/i })).toBeNull();
});

// Purpose: Confirms reopening a draft restores its saved values before further edits.
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
