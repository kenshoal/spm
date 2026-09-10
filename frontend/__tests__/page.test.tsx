import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import Home from "@/app/page";

test("renders the home page guidance", () => {
  render(<Home />);

  expect(
    screen.getByRole("heading", { name: /to get started/i }),
  ).toBeDefined();
  expect(screen.getByRole("link", { name: "Documentation" })).toBeDefined();
});
