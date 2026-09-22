import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

const session = vi.hoisted(() => ({ get: vi.fn(), set: vi.fn(), delete: vi.fn(), redirect: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: async () => session }));
vi.mock("next/navigation", () => ({ redirect: session.redirect }));

import { AuthForm } from "@/app/auth/auth-form";
import { login, logout, register } from "@/app/auth/actions";
import { requireEventOrganiser } from "@/lib/auth";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  session.get.mockReset();
  session.set.mockReset();
  session.delete.mockReset();
  session.redirect.mockReset();
});

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

test("stores a verified login in an HTTP-only cookie", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ access_token: "secret-token", expires_in: 3600 }),
  }));
  await login({}, credentials());
  expect(session.set).toHaveBeenCalledWith("cs_access_token", "secret-token", expect.objectContaining({ httpOnly: true, sameSite: "lax", maxAge: 3600 }));
  expect(session.redirect).toHaveBeenCalledWith("/event-requests");
});

test("logout clears the session cookie", async () => {
  await logout();
  expect(session.delete).toHaveBeenCalledWith("cs_access_token");
  expect(session.redirect).toHaveBeenCalledWith("/auth");
});

test("reports invalid credentials and an unavailable service", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));
  expect((await login({}, credentials())).success).not.toBe(true);
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  expect((await register({}, credentials())).message).toContain("unavailable");
});
