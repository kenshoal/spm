import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

const session = vi.hoisted(() => ({ get: vi.fn(), set: vi.fn(), delete: vi.fn(), redirect: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: async () => session }));
vi.mock("next/navigation", () => ({ redirect: session.redirect }));

import { AuthForm } from "@/app/auth/auth-form";
import { login, logout, register } from "@/app/auth/actions";
import { requireEventOrganiser, workspaceForRoles } from "@/lib/auth";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  session.get.mockReset();
  session.set.mockReset();
  session.delete.mockReset();
  session.redirect.mockReset();
});

// AC1-H1 (happy): an Organiser session passes the workspace guard without a redirect
test("allows an authenticated Event Organiser into the event-request workspace", async () => {
  session.get.mockReturnValue({ value: "valid-token" });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      id: "user-id",
      email: "organiser@example.com",
      role: "attendee",
      roles: ["attendee", "event_organiser"],
    }),
  }));

  await expect(requireEventOrganiser()).resolves.toMatchObject({ roles: ["attendee", "event_organiser"] });
  expect(session.redirect).not.toHaveBeenCalled();
});

// AC1-N2 (negative): a signed-in user without the organiser role is redirected to /unauthorised
test("redirects a signed-in user without the organiser role", async () => {
  session.get.mockReturnValue({ value: "valid-token" });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ id: "user-id", email: "admin@example.com", role: "admin" }),
  }));

  await requireEventOrganiser();
  expect(session.redirect).toHaveBeenCalledWith("/unauthorised");
});

function credentials() {
  const form = new FormData();
  form.set("email", "person@example.com");
  form.set("password", "long-password-123");
  return form;
}

// AC2-H4 (happy): the auth screen offers accessible log in and sign up forms
test("shows accessible login and sign-up forms", () => {
  render(<AuthForm />);
  expect(screen.getByRole("heading", { name: "Log in" })).toBeDefined();
  expect(screen.getByLabelText("Email")).toBeDefined();
  expect(screen.getByLabelText("Password")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  expect(screen.getByRole("heading", { name: "Create an account" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Create account" })).toBeDefined();
});

test("registers through authService and handles confirmation", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ email_confirmation_required: false }),
  });
  vi.stubGlobal("fetch", fetchMock);
  expect(await register({}, credentials())).toEqual({
    success: true,
    message: "Account created. You can log in now.",
  });
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8001/auth/register");
});

// AC2-H2 (happy): a valid login stores an HTTP-only session cookie and opens the workspace
test("stores a verified login in an HTTP-only cookie", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: "secret-token", expires_in: 3600 }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ role: "event_organiser", roles: ["event_organiser"] }),
    });
  vi.stubGlobal("fetch", fetchMock);
  await login({}, credentials());
  expect(session.set).toHaveBeenCalledWith("cs_access_token", "secret-token", expect.objectContaining({ httpOnly: true, sameSite: "lax", maxAge: 3600 }));
  expect(session.redirect).toHaveBeenCalledWith("/event-requests");
  expect(fetchMock.mock.calls[1]).toEqual([
    "http://127.0.0.1:8001/auth/me",
    expect.objectContaining({ headers: { Authorization: "Bearer secret-token" } }),
  ]);
});

// Purpose: A coordinator-only account must land in the workspace it can actually access.
// AC1-P2 (partition): a Coordinator lands in the coordination workspace after login
test("redirects a coordinator to assigned event requests after login", async () => {
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: "coordinator-token", expires_in: 3600 }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ role: "event_coordinator", roles: ["event_coordinator"] }),
    }));

  await login({}, credentials());

  expect(session.redirect).toHaveBeenCalledWith("/coordination/requests");
});

// Purpose: Multi-role and unsupported accounts receive a deterministic safe destination.
// AC1-P1…P6, AC3 (partition): every role opens its own workspace and a multi-role list is honoured
test("selects the default workspace from verified roles", () => {
  expect(workspaceForRoles(["event_coordinator", "event_organiser"])).toBe("/event-requests");
  expect(workspaceForRoles(["event_coordinator"])).toBe("/coordination/requests");
  expect(workspaceForRoles(["event_operations_manager"])).toBe("/operations/assignments");
  expect(workspaceForRoles(["venue_staff"])).toBe("/venues");
  expect(workspaceForRoles(["technical_support"])).toBe("/equipment");
  expect(workspaceForRoles(["attendee"])).toBe("/unauthorised");
});

// Purpose: A role lookup failure must not create a session whose destination is unknown.
// AC2-N2 (negative): a failed role verification stores no session cookie and redirects nowhere
test("does not store the session when workspace access cannot be verified", async () => {
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: "secret-token", expires_in: 3600 }),
    })
    .mockResolvedValueOnce({ ok: false, status: 503 }));

  expect(await login({}, credentials())).toEqual({
    message: "The authentication service could not verify your workspace access.",
  });
  expect(session.set).not.toHaveBeenCalled();
  expect(session.redirect).not.toHaveBeenCalled();
});

// AC2-X1 (cross-cutting): logout removes the session cookie so no stale session survives
test("logout clears the session cookie", async () => {
  await logout();
  expect(session.delete).toHaveBeenCalledWith("cs_access_token");
  expect(session.redirect).toHaveBeenCalledWith("/auth");
});

// AC3-N5 (negative): invalid credentials are reported without a success state
test("reports invalid credentials and an unavailable service", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));
  expect((await login({}, credentials())).success).not.toBe(true);
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  expect((await register({}, credentials())).message).toContain("unavailable");
});
