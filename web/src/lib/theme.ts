import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";
const listeners = new Set<() => void>();

function current(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function setTheme(t: Theme) {
  document.documentElement.classList.toggle("dark", t === "dark");
  try {
    localStorage.setItem("ats-theme", t);
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

export function toggleTheme() {
  setTheme(current() === "dark" ? "light" : "dark");
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
