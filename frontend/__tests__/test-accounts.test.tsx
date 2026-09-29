import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { TestAccounts } from "@/app/auth/test-accounts";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

const seededEmails = [
  "admin@example.com",
  "attendee@example.com",
  "event_coordinator1@example.com",
  "event_coordinator2@example.com",
  "event_operations_manager@example.com",
  "event_organiser@example.com",
  "technical_support@example.com",
  "venue_staff@example.com",
];

test("lists every seeded test account and their shared password during development", () => {
  vi.stubEnv("NODE_ENV", "development");
  render(<TestAccounts />);

  for (const email of seededEmails) {
    expect(screen.getByText(email)).toBeTruthy();
  }
  expect(screen.getByText("12345678")).toBeTruthy();
});

test("is left out of production builds so the credentials never reach a live site", () => {
  vi.stubEnv("NODE_ENV", "production");
  const { container } = render(<TestAccounts />);

  expect(container.innerHTML).toBe("");
});
