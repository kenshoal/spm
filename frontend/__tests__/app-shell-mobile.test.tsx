import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("../app/auth/actions", () => ({ logout: vi.fn() }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));

import { AppShell } from "../app/components/app-shell";

// AC18-H1 (happy, hotfix 18): workspace links are never hidden on a phone
test("keeps the workspace links visible at phone width", () => {
  render(<AppShell signedIn navLinks={[{ href: "/safety", label: "Safety checks" }]}>x</AppShell>);

  const nav = screen.getByRole("navigation", { name: "Workspaces" });
  expect(nav.className.split(" ")).not.toContain("hidden");
  expect(nav.className).toContain("w-full");
  expect(screen.getByRole("link", { name: "Safety checks" }).getAttribute("href")).toBe("/safety");
});
