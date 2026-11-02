import { useEffect, useState } from "react";

export type Side = "left" | "right";
type Widths = Record<Side, number>;

const STORAGE_KEY = "panelWidths";
export const DEFAULT_WIDTHS: Widths = { left: 300, right: 290 };
export const LIMITS: Record<Side, { min: number; max: number }> = {
  left: { min: 200, max: 640 },
  right: { min: 220, max: 640 },
};
const MIN_MIDDLE = 420;

function load(): Widths {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (typeof stored?.left === "number" && typeof stored?.right === "number") return stored;
  } catch {
    return DEFAULT_WIDTHS;
  }
  return DEFAULT_WIDTHS;
}

export function usePanelWidths() {
  const [widths, setWidths] = useState<Widths>(load);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(widths));
  }, [widths]);

  const resize = (side: Side, width: number) => {
    setWidths((current) => {
      const other = side === "left" ? current.right : current.left;
      const roomForMiddle = window.innerWidth - other - MIN_MIDDLE;
      const max = Math.min(LIMITS[side].max, Math.max(LIMITS[side].min, roomForMiddle));
      const next = Math.round(Math.min(max, Math.max(LIMITS[side].min, width)));
      return next === current[side] ? current : { ...current, [side]: next };
    });
  };

  return { widths, resize };
}
