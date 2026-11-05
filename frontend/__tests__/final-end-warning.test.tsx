import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { FinalEndWarning } from "@/app/coordination/requests/[id]/final-end-warning";

afterEach(cleanup);

// SCRUM-40 AC9-H1, AC9-H2 (happy): a Confirmed or Planning event with no recorded end shows a warning
test.each(["Confirmed", "Planning"] as const)("warns that a %s event has no final end recorded", (status) => {
  render(<FinalEndWarning status={status} finalEventEndAt={null} />);

  const warning = screen.getByRole("status");
  expect(warning.textContent).toMatch(/no final event end recorded/i);
  expect(warning.textContent).toMatch(/not complete automatically/i);
});

// SCRUM-40 AC9-N1 (negative): a recorded end shows no warning
test.each(["Confirmed", "Planning"] as const)("shows no warning once a %s event has its end", (status) => {
  render(<FinalEndWarning status={status} finalEventEndAt="2026-11-20T10:00:00Z" />);

  expect(screen.queryByRole("status")).toBeNull();
});

// SCRUM-40 AC9-P1 (partition): the other statuses show no warning, an end is not due yet or never will be
test.each(["Approved", "Under Review", "Safety Review", "Completed", "Cancelled", "Postponed"] as const)(
  "shows no warning for a %s event",
  (status) => {
    render(<FinalEndWarning status={status} finalEventEndAt={null} />);

    expect(screen.queryByRole("status")).toBeNull();
  },
);

// SCRUM-40 AC9-X1 (cross-cutting): a Confirmed event cannot take an end any more, so the warning says what to do instead
test("a Confirmed event is told how to proceed without an end", () => {
  render(<FinalEndWarning status="Confirmed" finalEventEndAt={null} />);

  expect(screen.getByRole("status").textContent).toMatch(/mark the event completed yourself/i);
});

// SCRUM-40 AC9-X2 (cross-cutting): a Planning event is told to record the end
test("a Planning event is told to record the end before the safety check", () => {
  render(<FinalEndWarning status="Planning" finalEventEndAt={null} />);

  expect(screen.getByRole("status").textContent).toMatch(/record the final event end/i);
});
