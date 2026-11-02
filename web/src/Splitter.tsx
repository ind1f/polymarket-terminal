import type { KeyboardEvent, PointerEvent } from "react";
import { DEFAULT_WIDTHS, LIMITS, type Side } from "./usePanelWidths";

type Props = {
  side: Side;
  width: number;
  label: string;
  onResize: (side: Side, width: number) => void;
};

const STEP = 20;

export function Splitter({ side, width, label, onResize }: Props) {
  const direction = side === "left" ? 1 : -1;

  const startDrag = (down: PointerEvent<HTMLDivElement>) => {
    if (down.button !== 0) return;
    down.preventDefault();
    const handle = down.currentTarget;
    const startX = down.clientX;
    handle.setPointerCapture(down.pointerId);
    document.body.classList.add("resizing");

    const move = (event: globalThis.PointerEvent) =>
      onResize(side, width + direction * (event.clientX - startX));
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
      handle.removeEventListener("pointercancel", stop);
      document.body.classList.remove("resizing");
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
  };

  const nudge = (key: KeyboardEvent<HTMLDivElement>) => {
    if (key.key !== "ArrowLeft" && key.key !== "ArrowRight") return;
    key.preventDefault();
    const sign = key.key === "ArrowRight" ? 1 : -1;
    onResize(side, width + direction * sign * STEP);
  };

  return (
    <div
      className={`splitter splitter-${side}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={LIMITS[side].min}
      aria-valuemax={LIMITS[side].max}
      tabIndex={0}
      onPointerDown={startDrag}
      onDoubleClick={() => onResize(side, DEFAULT_WIDTHS[side])}
      onKeyDown={nudge}
    />
  );
}
