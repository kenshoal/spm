import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({ id: "tech-1", email: "tech@example.com", role: "technical_support", roles: ["technical_support"] }),
}));

import { changeEquipmentStatus, createEquipment, updateEquipmentQuantity } from "@/app/equipment/actions";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// Purpose: SCRUM-45 AC1 — creating posts the record and opens its detail page.
test("creates equipment and opens its record", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "eq-1" }) });
  vi.stubGlobal("fetch", fetchMock);

  await expect(createEquipment({}, form({ type: "Projector", total_owned_quantity: "3", home_location: "Store A", operational_status: "AVAILABLE" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8002/equipment");
  expect(navigation.redirect).toHaveBeenCalledWith("/equipment/eq-1");
});

// Purpose: Invalid input never reaches the API.
test("does not call the API when the form is invalid", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await createEquipment({}, form({ type: "", total_owned_quantity: "-1", home_location: "" }));

  expect(state.message).toBe("Check the highlighted fields.");
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: Ruling 2 (Task 7 controller ruling) — React resets uncontrolled form
// fields to their defaultValue as soon as the action is submitted, even on a
// validation error. Without echoing the raw typed values back, a failed create
// would blank out fields the user filled in correctly.
test("an invalid create echoes the raw submitted values", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await createEquipment({}, form({
    type: "  Projector  ",
    total_owned_quantity: "-1",
    home_location: "Store A",
    operational_status: "DAMAGED",
  }));

  expect(state.values).toEqual({
    type: "Projector",
    description: "",
    total_owned_quantity: "-1",
    home_location: "Store A",
    operational_status: "DAMAGED",
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: SCRUM-45 AC2 — updating the owned quantity patches only the quantity.
test("updates the total owned quantity", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await updateEquipmentQuantity("eq-1", {}, form({ total_owned_quantity: "9" }));

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8002/equipment/eq-1/quantity");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH", body: JSON.stringify({ total_owned_quantity: 9 }) });
  expect(state).toEqual({ saved: true, message: "Quantity updated." });
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/equipment/eq-1");
});

// Purpose: Review focus 4 / Ruling 2b — a bad quantity is reported inline and the
// raw invalid text ("2.5") is echoed back rather than silently reverting to the
// stored quantity.
test("rejects a non-whole quantity", async () => {
  vi.stubGlobal("fetch", vi.fn());

  const state = await updateEquipmentQuantity("eq-1", {}, form({ total_owned_quantity: "2.5" }));

  expect(state).toEqual({ message: "Enter a whole number of zero or more.", values: { total_owned_quantity: "2.5" } });
});

// Purpose: Equipment removed since the page loaded is explained.
test("explains missing equipment", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  const state = await updateEquipmentQuantity("eq-1", {}, form({ total_owned_quantity: "4" }));

  expect(state).toEqual({ message: "This equipment record no longer exists.", values: { total_owned_quantity: "4" } });
});

// Purpose: SCRUM-16 AC1 — marking equipment damaged sends the status and reason.
test("changes the operational status with a reason", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await changeEquipmentStatus("eq-1", "AVAILABLE", {}, form({ new_status: "DAMAGED", reason: "  Cracked lens " }));

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8002/equipment/eq-1/status");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH", body: JSON.stringify({ new_status: "DAMAGED", reason: "Cracked lens" }) });
  expect(state).toEqual({ saved: true, message: "Status changed to Damaged." });
});

// Purpose: A status change must actually change something, and use a known status.
test("refuses an unchanged or unknown status", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  expect(await changeEquipmentStatus("eq-1", "DAMAGED", {}, form({ new_status: "DAMAGED" }))).toEqual({
    message: "Choose a different status.",
    values: { new_status: "DAMAGED", reason: "" },
  });
  expect(await changeEquipmentStatus("eq-1", "DAMAGED", {}, form({ new_status: "LOST" }))).toEqual({
    message: "Choose a different status.",
    values: { new_status: "LOST", reason: "" },
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: The backend's 255-character reason limit is enforced before sending.
test("rejects an overlong reason", async () => {
  vi.stubGlobal("fetch", vi.fn());

  const state = await changeEquipmentStatus("eq-1", "AVAILABLE", {}, form({ new_status: "DAMAGED", reason: "x".repeat(256) }));

  expect(state).toEqual({
    message: "Keep the reason to 255 characters or fewer.",
    values: { new_status: "DAMAGED", reason: "x".repeat(256) },
  });
});

// Purpose: Ruling 4 — an overlong reason must echo the raw (trimmed) reason back
// so a corrected resubmission doesn't lose what the user typed.
test("echoes the raw reason back when it is too long", async () => {
  vi.stubGlobal("fetch", vi.fn());

  const state = await changeEquipmentStatus("eq-1", "AVAILABLE", {}, form({ new_status: "DAMAGED", reason: `  ${"y".repeat(260)}  ` }));

  expect(state).toEqual({
    message: "Keep the reason to 255 characters or fewer.",
    values: { new_status: "DAMAGED", reason: "y".repeat(260) },
  });
});
