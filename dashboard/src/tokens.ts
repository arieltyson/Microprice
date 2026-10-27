// Every colour in the dashboard, defined once as numbers so tests can check it.
// CSS custom properties are generated from these values in theme.ts.

export type Rgb = readonly [number, number, number];

export interface Palette {
  base: Rgb;
  surface: Rgb;
  raised: Rgb;
  separator: Rgb;
  textPrimary: Rgb;
  textSecondary: Rgb;
  textTertiary: Rgb;
  accent: Rgb; // equals the dot in the mark (public/favicon.svg)
  onAccent: Rgb;
  bid: Rgb; // blue: bids, buys, positive P&L
  ask: Rgb; // orange: asks, sells, negative P&L
  gap: Rgb; // hatching for feed gaps
  warning: Rgb; // operational alerts only, never P&L
}

export type ThemeName = "light" | "dark" | "lightHighContrast" | "darkHighContrast";

export const palettes: Record<ThemeName, Palette> = {
  light: {
    base: [250, 250, 249],
    surface: [255, 255, 255],
    raised: [243, 243, 241],
    separator: [212, 212, 207],
    textPrimary: [24, 24, 27],
    textSecondary: [72, 72, 78],
    textTertiary: [104, 104, 110],
    accent: [34, 120, 34],
    onAccent: [255, 255, 255],
    bid: [29, 95, 168],
    ask: [168, 80, 0],
    gap: [150, 150, 150],
    warning: [140, 90, 0],
  },
  dark: {
    base: [17, 17, 19],
    surface: [25, 25, 28],
    raised: [34, 34, 38],
    separator: [62, 62, 68],
    textPrimary: [236, 236, 238],
    textSecondary: [190, 190, 196],
    textTertiary: [156, 156, 162],
    accent: [104, 196, 108],
    onAccent: [17, 17, 19],
    bid: [112, 168, 238],
    ask: [236, 150, 82],
    gap: [110, 110, 116],
    warning: [232, 184, 72],
  },
  lightHighContrast: {
    base: [255, 255, 255],
    surface: [255, 255, 255],
    raised: [238, 238, 236],
    separator: [96, 96, 100],
    textPrimary: [0, 0, 0],
    textSecondary: [32, 32, 36],
    textTertiary: [56, 56, 62],
    accent: [18, 88, 22],
    onAccent: [255, 255, 255],
    bid: [12, 62, 128],
    ask: [128, 56, 0],
    gap: [96, 96, 100],
    warning: [102, 64, 0],
  },
  darkHighContrast: {
    base: [0, 0, 0],
    surface: [8, 8, 10],
    raised: [24, 24, 28],
    separator: [150, 150, 156],
    textPrimary: [255, 255, 255],
    textSecondary: [228, 228, 232],
    textTertiary: [200, 200, 206],
    accent: [140, 226, 142],
    onAccent: [0, 0, 0],
    bid: [150, 196, 255],
    ask: [255, 180, 118],
    gap: [150, 150, 156],
    warning: [255, 210, 110],
  },
};

// WCAG 2.2 relative luminance, including the sRGB gamma expansion.
export function luminance([r, g, b]: Rgb): number {
  const linear = (channel: number) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export function hue([r, g, b]: Rgb): number {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max === min) return 0;
  const d = max - min;
  let h: number;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

export function hueDistance(a: Rgb, b: Rgb): number {
  const d = Math.abs(hue(a) - hue(b));
  return Math.min(d, 360 - d);
}

export const css = ([r, g, b]: Rgb): string => `rgb(${r} ${g} ${b})`;

// Spacing on a 4px grid and the type scale, both in rem so user settings apply.
export const space = { 1: "0.25rem", 2: "0.5rem", 3: "0.75rem", 4: "1rem", 6: "1.5rem", 8: "2rem", 12: "3rem" };
export const radius = { small: "0.25rem", control: "0.375rem", panel: "0.5rem" };
export const MIN_TARGET_PX = 24; // WCAG 2.2 success criterion 2.5.8
export const TERTIARY_MIN_REM = 0.875;
