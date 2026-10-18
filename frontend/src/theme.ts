/**
 * Runtime theme handling. The Tailwind palette is emitted as CSS channel
 * variables (see tailwind.config.js + index.css), so switching the `dark`
 * class on <html> repaints every utility. Charts need literal hex colors,
 * so they read `chartColors()`. App does NOT key the route outlet by theme:
 * components stay mounted across a toggle and re-render by subscribing with
 * `useTheme()`, which preserves page state (inputs, loaded data, open views).
 */
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const THEME_KEY = "noesis_theme";
const THEME_EVENT = "noesis:themechange";

export function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/** Subscribe to theme changes; returns an unsubscribe function. */
export function subscribeTheme(listener: () => void): () => void {
  window.addEventListener(THEME_EVENT, listener);
  return () => window.removeEventListener(THEME_EVENT, listener);
}

/**
 * Reactive theme for React components. Re-renders the subscriber on every
 * toggle WITHOUT unmounting it, so page state survives light/dark switches.
 */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribeTheme, currentTheme, currentTheme);
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private mode: theme still applies for this session */
  }
  // Notify subscribers (Plot, pages) so they repaint in place — no remount.
  window.dispatchEvent(new Event(THEME_EVENT));
}

/** Called once from main.tsx (index.html also runs a pre-paint snippet). */
export function initTheme(): void {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(THEME_KEY);
  } catch {
    /* ignore */
  }
  applyTheme(stored === "dark" ? "dark" : "light");
}

export interface ChartColors {
  /** axis gridlines */
  grid: string;
  /** primary ink (titles, markers, curves) */
  ink: string;
  /** secondary text inside plots (annotations, legend text) */
  muted: string;
  /** plot area background */
  panel: string;
  /** highlight color for reference markers */
  ref: string;
}

export function chartColors(theme: Theme = currentTheme()): ChartColors {
  if (theme === "dark") {
    return {
      grid: "#1e293b",
      ink: "#e2e8f0",
      muted: "#94a3b8",
      panel: "rgba(15,23,42,0.4)",
      ref: "#ffd54f",
    };
  }
  return {
    grid: "#e6e6df",
    ink: "#111111",
    muted: "#6b6b66",
    panel: "rgba(255,255,255,0)",
    ref: "#ffd54f",
  };
}
