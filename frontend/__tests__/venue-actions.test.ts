import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({ id: "staff-1", email: "staff@example.com", role: "venue_staff", roles: ["venue_staff"] }),
}));

import { createVenue, updateVenue } from "@/app/venues/actions";

function form(fields: {
  name?: string;
  location?: string;
  max_capacity?: string;
  facilities?: string;
  accessibility_features?: string;
  supported_layouts?: string[];
  operating_slots?: string[];
  status?: string;
}): FormData {
  const data = new FormData();
  if (fields.name !== undefined) data.set("name", fields.name);
  if (fields.location !== undefined) data.set("location", fields.location);
  if (fields.max_capacity !== undefined) data.set("max_capacity", fields.max_capacity);
  if (fields.facilities !== undefined) data.set("facilities", fields.facilities);
  if (fields.accessibility_features !== undefined) data.set("accessibility_features", fields.accessibility_features);
  for (const layout of fields.supported_layouts ?? []) data.append("supported_layouts", layout);
  for (const slot of fields.operating_slots ?? []) data.append("operating_slots", slot);
  if (fields.status !== undefined) data.set("status", fields.status);
  return data;
}

const validFields = { name: "Hall A", location: "Building 1", max_capacity: "50" };

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// SCRUM-30 AC1-H1 (happy): a valid create posts the parsed payload and opens the venue list
// Purpose: A valid create posts the parsed payload and opens the venue list.
test("creates a venue and redirects to the venue list", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "v1" }) });
  vi.stubGlobal("fetch", fetchMock);

  await expect(createVenue({}, form(validFields))).rejects.toThrow("NEXT_REDIRECT");

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8004/venues");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "POST",
    body: JSON.stringify({
      name: "Hall A",
      location: "Building 1",
      max_capacity: 50,
      facilities: [],
      accessibility_features: [],
      supported_layouts: [],
      setup_minutes: 0,
      turnaround_minutes: 0,
    }),
  });
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/venues");
  expect(navigation.redirect).toHaveBeenCalledWith("/venues");
});

// SCRUM-30 AC1-N5 (negative): invalid form values are echoed raw and never sent to the venue service
// Purpose: Invalid input never reaches the API and the raw values are echoed
// back so a corrected resubmission doesn't lose what was typed.
test("an invalid form never calls fetch and echoes the raw values", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await createVenue({}, form({ name: "", location: "", max_capacity: "" }));

  expect(state.message).toBe("Check the highlighted fields.");
  expect(state.values).toEqual({
    name: "",
    location: "",
    max_capacity: "",
    facilities: "",
    accessibility_features: "",
    supported_layouts: [],

    setup_minutes: "",

    turnaround_minutes: "",
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

// SCRUM-30 AC1-N1 (negative): a refused create explains that only Venue Staff can change the catalogue
// Purpose: Only Venue Staff may change the catalogue; the backend's refusal is explained.
test("a 403 explains that only Venue Staff can change the catalogue", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));

  const state = await createVenue({}, form(validFields));

  expect(state.message).toBe("Only Venue Staff can change the venue catalogue.");
  expect(state.values).toEqual({
    name: "Hall A",
    location: "Building 1",
    max_capacity: "50",
    facilities: "",
    accessibility_features: "",
    supported_layouts: [],

    setup_minutes: "",

    turnaround_minutes: "",
  });
});

// SCRUM-30 AC1-N3 (negative): updating a venue removed since the page loaded is explained, not created
// Purpose: A venue removed since the page loaded is explained.
test("a 404 on update explains the venue no longer exists", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  const state = await updateVenue("v1", {}, form({ ...validFields, status: "available" }));

  expect(state.message).toBe("This venue no longer exists.");
});

// Purpose: A backend 422 doesn't highlight any field (validation already
// passed client-side), so the wording must not claim one is highlighted.
test("a backend 422 is worded without referring to highlighted fields", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422 }));

  const state = await createVenue({}, form(validFields));

  expect(state.message).toBe("The venue service rejected these details. Check them and try again.");
  expect(state.values).toEqual({
    name: "Hall A",
    location: "Building 1",
    max_capacity: "50",
    facilities: "",
    accessibility_features: "",
    supported_layouts: [],

    setup_minutes: "",

    turnaround_minutes: "",
  });
});

// Purpose: An expired session sends the venue staffer to sign in.
test("redirects to sign-in when the session has expired", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

  await expect(createVenue({}, form(validFields))).rejects.toThrow("NEXT_REDIRECT");
  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// Purpose: An unreachable venue service leaves the staffer on the page with a
// retryable error, with the typed values still in place.
test("returns a retryable error when the venue service cannot be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

  const state = await createVenue({}, form(validFields));

  expect(state.message).toBe("The venue could not be saved. Please try again.");
  expect(state.values).toEqual({
    name: "Hall A",
    location: "Building 1",
    max_capacity: "50",
    facilities: "",
    accessibility_features: "",
    supported_layouts: [],

    setup_minutes: "",

    turnaround_minutes: "",
  });
});
