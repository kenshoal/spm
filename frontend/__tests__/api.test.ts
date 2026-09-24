import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token" }));

import { getJson, readDetail, sendJson } from "@/lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
});

// Purpose: Reads carry the session token and are never cached across users.
test("getJson sends the bearer token and parses the body", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [{ id: "v1" }],
  });
  vi.stubGlobal("fetch", fetchMock);

  await expect(getJson("http://svc", "/venues")).resolves.toEqual([{ id: "v1" }]);
  expect(fetchMock).toHaveBeenCalledWith("http://svc/venues", {
    headers: { Authorization: "Bearer valid-token" },
    cache: "no-store",
  });
});

// Purpose: A missing record is a normal outcome the page renders, not a crash.
test("getJson returns null for 404", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  await expect(getJson("http://svc", "/venues/x")).resolves.toBeNull();
});

// Purpose: An expired session goes to sign-in rather than an error page.
test("getJson redirects to sign-in on 401", async () => {
  navigation.redirect.mockImplementation(() => {
    throw new Error("NEXT_REDIRECT");
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

  await expect(getJson("http://svc", "/venues")).rejects.toThrow("NEXT_REDIRECT");
  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// Purpose: Other failures surface so the page can show "service unavailable".
test("getJson throws on server errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

  await expect(getJson("http://svc", "/venues")).rejects.toThrow();
});

// Purpose: Writes send JSON with the token and leave status handling to the caller.
test("sendJson posts JSON without redirecting", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 });
  vi.stubGlobal("fetch", fetchMock);

  const response = await sendJson("http://svc", "/venues", "POST", { name: "Hall" });

  expect(response.status).toBe(401);
  expect(navigation.redirect).not.toHaveBeenCalled();
  expect(fetchMock).toHaveBeenCalledWith("http://svc/venues", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer valid-token" },
    body: JSON.stringify({ name: "Hall" }),
  });
});

// Purpose: Backend explanations reach the user only when they are plain strings.
test("readDetail extracts a string detail and tolerates anything else", async () => {
  await expect(readDetail({ json: async () => ({ detail: "No." }) } as Response)).resolves.toBe("No.");
  await expect(readDetail({ json: async () => ({ detail: [{ msg: "x" }] }) } as Response)).resolves.toBeNull();
  await expect(readDetail({ json: async () => { throw new Error("bad"); } } as unknown as Response)).resolves.toBeNull();
});
