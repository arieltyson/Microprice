import { describe, expect, it } from "vitest";
import { formatClock, formatPrice, formatSigned, formatUsdFromTicks } from "./format";

describe("formatters", () => {
  it("formats ticks as signed dollars with a real minus sign", () => {
    expect(formatUsdFromTicks(12345)).toBe("+$123.45");
    expect(formatUsdFromTicks(-250)).toBe("−$2.50");
    expect(formatUsdFromTicks(0)).toBe("$0.00");
  });

  it("formats prices and signed integers", () => {
    expect(formatPrice(23001)).toBe("230.01");
    expect(formatSigned(-300)).toBe("−300");
  });

  it("formats the session clock", () => {
    expect(formatClock(34_200)).toBe("09:30:00");
  });
});
