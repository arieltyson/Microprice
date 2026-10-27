import { describe, expect, it } from "vitest";
import { contrast, hue, hueDistance, luminance, palettes, type Palette, type ThemeName } from "./tokens";

const themes = Object.keys(palettes) as ThemeName[];
const backgrounds: (keyof Palette)[] = ["base", "surface", "raised"];

describe("contrast math", () => {
  it("matches the WCAG reference values", () => {
    expect(contrast([0, 0, 0], [255, 255, 255])).toBeCloseTo(21, 5);
    expect(contrast([118, 118, 118], [255, 255, 255])).toBeCloseTo(4.54, 2);
  });

  it("uses gamma expansion rather than a channel average", () => {
    // A naive average would put mid grey at 0.5; the real luminance is far lower.
    expect(luminance([128, 128, 128])).toBeCloseTo(0.2158, 3);
  });

  it("computes hue angles", () => {
    expect(hue([255, 0, 0])).toBe(0);
    expect(hue([0, 255, 0])).toBe(120);
    expect(hue([0, 0, 255])).toBe(240);
  });
});

describe.each(themes)("%s theme", (name) => {
  const p = palettes[name];

  it.each(backgrounds)("body text meets 4.5:1 on %s", (bg) => {
    for (const text of ["textPrimary", "textSecondary", "textTertiary"] as const) {
      expect(contrast(p[text], p[bg]), `${text} on ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(backgrounds)("data colours and the accent meet 3:1 on %s", (bg) => {
    for (const key of ["bid", "ask", "accent", "warning"] as const) {
      expect(contrast(p[key], p[bg]), `${key} on ${bg}`).toBeGreaterThanOrEqual(3);
    }
  });

  it("text on the accent meets 4.5:1", () => {
    expect(contrast(p.onAccent, p.accent)).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps the accent at least 90 degrees from bid and ask", () => {
    expect(hueDistance(p.accent, p.bid)).toBeGreaterThanOrEqual(90);
    expect(hueDistance(p.accent, p.ask)).toBeGreaterThanOrEqual(90);
  });

  it("keeps bid and ask distinguishable in greyscale", () => {
    expect(Math.abs(luminance(p.bid) - luminance(p.ask))).toBeGreaterThan(0.005);
  });
});

describe("high-contrast themes", () => {
  it.each([
    ["light", "lightHighContrast"],
    ["dark", "darkHighContrast"],
  ] as const)("%s high contrast raises every text pairing", (standard, high) => {
    for (const text of ["textPrimary", "textSecondary", "textTertiary"] as const) {
      expect(contrast(palettes[high][text], palettes[high].base)).toBeGreaterThan(
        contrast(palettes[standard][text], palettes[standard].base),
      );
    }
  });
});
