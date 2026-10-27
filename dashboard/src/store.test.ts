import { describe, expect, it } from "vitest";
import { emptyState, MAX_POINTS, reduce, type TickMessage } from "./store";

const tick = (t: number, overrides: Partial<TickMessage> = {}): TickMessage => ({
  type: "tick",
  t,
  mid: 23000,
  micro: 23000.2,
  equity: 100,
  spreadCapture: 150,
  inventory: 200,
  bids: [[22999, 500]],
  asks: [[23001, 300]],
  lastTrade: 23000,
  gap: false,
  fills: [],
  ...overrides,
});

describe("live reducer", () => {
  it("splits P&L into spread capture and inventory P&L", () => {
    const state = reduce(emptyState(), [tick(34_201)]);
    expect(state.spreadCapture).toEqual([150]);
    expect(state.inventoryPnl).toEqual([-50]);
    expect(state.status).toBe("live");
  });

  it("records feed gaps as null, never as zero", () => {
    const state = reduce(emptyState(), [tick(1), tick(2, { gap: true }), tick(3)]);
    expect(state.equity).toEqual([100, null, 100]);
    expect(state.gaps).toBe(1);
  });

  it("keeps a bounded history", () => {
    const many = Array.from({ length: MAX_POINTS + 10 }, (_, i) => tick(i));
    const state = reduce(emptyState(), many);
    expect(state.times.length).toBe(MAX_POINTS);
    expect(state.times[0]).toBe(10);
  });

  it("resets on a new session and marks the end", () => {
    const first = reduce(emptyState(), [tick(1)]);
    const next = reduce(first, [{ type: "meta", symbol: "AAPL", date: "2026-10-22", variant: "signal" }]);
    expect(next.times).toEqual([]);
    expect(reduce(next, [{ type: "end" }]).status).toBe("ended");
  });
});
