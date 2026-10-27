import { useSyncExternalStore } from "react";

// Every transition goes through this hook, so reduced motion cannot be forgotten.
const query = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;

function subscribe(onChange: () => void): () => void {
  query?.addEventListener("change", onChange);
  return () => query?.removeEventListener("change", onChange);
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, () => query?.matches ?? false, () => false);
}

/** Returns a CSS transition value, or "none" when the user asked for reduced motion. */
export function useMotion(transition: string): string {
  return usePrefersReducedMotion() ? "none" : transition;
}
