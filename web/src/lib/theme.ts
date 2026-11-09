// Theme = data-theme attribute on <html> ("light" | "dark"). With no stored choice the
// system preference applies (tokens.css handles prefers-color-scheme), but we still
// set the attribute so components can react to it.
import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";
const listeners = new Set<() => void>();
const KEY = "ats-theme";

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function current(): Theme {
  const t = document.documentElement.getAttribute("data-theme");
  return t === "dark" || t === "light" ? t : systemTheme();
}

export function setTheme(t: Theme, persist = true) {
  document.documentElement.setAttribute("data-theme", t);
  if (persist) {
    try {
      localStorage.setItem(KEY, t);
    } catch {
      /* ignore */
    }
  }
  listeners.forEach((l) => l());
}

export function toggleTheme() {
  setTheme(current() === "dark" ? "light" : "dark");
}

// follow the OS while the user has not chosen explicitly
if (typeof window !== "undefined" && window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(KEY);
    } catch {
      /* ignore */
    }
    if (!stored) setTheme(systemTheme(), false);
  });
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    current,
    () => "light",
  );
}
