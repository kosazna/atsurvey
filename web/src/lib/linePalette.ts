import { useMemo } from "react";
import { assignColors, LINE_PALETTE_TOKENS } from "./linework";
import { useTheme } from "./theme";
import { tokenColor } from "./tokens";

/** Resolved categorical palette for line codes (follows theme and token changes). */
export function useLinePalette(): string[] {
  const theme = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => LINE_PALETTE_TOKENS.map((n) => tokenColor(n)), [theme]);
}

/** Stable code → colour map for the given codes. */
export function useLineColors(codes: string[]): Record<string, string> {
  const palette = useLinePalette();
  const key = [...codes].sort().join("|");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => assignColors(codes, palette), [key, palette]);
}
