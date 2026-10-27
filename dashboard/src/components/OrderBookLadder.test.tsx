import { cleanup, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it } from "vitest";
import { OrderBookLadder } from "./OrderBookLadder";

describe("OrderBookLadder", () => {
  afterEach(cleanup);

  const props = {
    bids: [[22999, 500], [22998, 1200]] as const,
    asks: [[23001, 300], [23002, 900]] as const,
    micro: 22999.7,
    lastTrade: 23001,
  };

  it("is a table with row and column headers", () => {
    render(<OrderBookLadder {...props} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Bid size", "Price", "Ask size"]);
    expect(screen.getAllByRole("rowheader").length).toBeGreaterThanOrEqual(4);
  });

  it("describes the micro-price relative to the touch", () => {
    render(<OrderBookLadder {...props} />);
    expect(screen.getByRole("table").querySelector("caption")?.textContent).toContain(
      "Micro-price 230.00, between the best bid 229.99 and best ask 230.01",
    );
  });

  it("has no axe violations", async () => {
    const { container } = render(<OrderBookLadder {...props} />);
    const results = await axe.run(container, { rules: { region: { enabled: false } } });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});
