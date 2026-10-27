import { css, palettes, type Palette, type ThemeName } from "./tokens";

export type ThemeChoice = "system" | "light" | "dark";
const STORAGE_KEY = "microprice.theme";

function kebab(key: string): string {
  return key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

export function resolveTheme(choice: ThemeChoice): ThemeName {
  const dark = choice === "dark" || (choice === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  const high = matchMedia("(prefers-contrast: more)").matches;
  if (dark) return high ? "darkHighContrast" : "dark";
  return high ? "lightHighContrast" : "light";
}

export function applyTheme(choice: ThemeChoice): ThemeName {
  const name = resolveTheme(choice);
  const palette: Palette = palettes[name];
  const root = document.documentElement;
  for (const [key, value] of Object.entries(palette)) {
    root.style.setProperty(`--color-${kebab(key)}`, css(value));
  }
  root.dataset.theme = name;
  root.style.colorScheme = name.startsWith("dark") ? "dark" : "light";
  return name;
}

export function savedTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function saveTheme(choice: ThemeChoice): void {
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Storage can be unavailable (private windows); the choice still applies for this visit.
  }
}

export function currentColor(name: keyof Palette): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--color-${kebab(name)}`).trim();
}
