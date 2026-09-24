import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/equipment/actions", () => ({ changeEquipmentStatus: vi.fn(), updateEquipmentQuantity: vi.fn(), createEquipment: vi.fn() }));

import { StatusForm } from "@/app/equipment/[id]/status-form";
import { StatusHistory } from "@/app/equipment/[id]/status-history";

afterEach(cleanup);

// Purpose: The status picker never offers the status the equipment already has.
test("offers every status except the current one", () => {
  render(<StatusForm equipmentId="eq-1" currentStatus="AVAILABLE" />);

  const options = within(screen.getByRole("combobox", { name: "New status" })).getAllByRole("option");
  expect(options.map((option) => option.textContent)).toEqual(["Damaged", "Under repair", "Under maintenance", "Retired"]);
});

// Purpose: SCRUM-16 AC3 — each change shows who made it and when.
test("lists each change with who and when", () => {
  render(
    <StatusHistory
      entries={[{ id: 2, equipment_id: "eq-1", old_status: "AVAILABLE", new_status: "DAMAGED", reason: "Dropped", changed_by: "tech-1", changed_at: "2026-09-20T02:00:00Z" }]}
    />,
  );

  const item = screen.getByRole("listitem");
  expect(item.textContent).toContain("Available → Damaged");
  expect(item.textContent).toContain("Dropped");
  expect(item.textContent).toContain("tech-1");
  expect(item.textContent).toMatch(/20 Sept? 2026/);
});

// Purpose: An empty history explains itself.
test("explains an empty history", () => {
  render(<StatusHistory entries={[]} />);

  expect(screen.getByText("No status changes recorded yet.")).toBeDefined();
});
