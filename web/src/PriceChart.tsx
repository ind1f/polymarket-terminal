import {
  ColorType,
  createChart,
  LineSeries,
  type AutoscaleInfo,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { PricePoint } from "./api";
import { cents } from "./format";

export function PriceChart({ points, resetKey }: { points: PricePoint[]; resetKey: string }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi>(null);
  const series = useRef<ISeriesApi<"Line">>(null);
  const fittedKey = useRef<string>(null);

  useEffect(() => {
    const instance = createChart(container.current!, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#6b6b6b",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#efefef" } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.04, bottom: 0.04 } },
      timeScale: { borderVisible: false, timeVisible: true },
    });
    series.current = instance.addSeries(LineSeries, {
      color: "#000000",
      lineWidth: 2,
      priceLineVisible: false,
      priceFormat: { type: "custom", formatter: cents, minMove: 0.001 },
      autoscaleInfoProvider: (baseImplementation: () => AutoscaleInfo | null) => {
        const info = baseImplementation();
        if (!info?.priceRange) return info;
        const { minValue, maxValue } = info.priceRange;
        return {
          ...info,
          priceRange: { minValue: Math.max(minValue, 0), maxValue: Math.min(maxValue, 1) },
        };
      },
    });
    chart.current = instance;
    return () => {
      instance.remove();
      chart.current = null;
      series.current = null;
    };
  }, []);

  useEffect(() => {
    series.current?.setData(
      points.map((point) => ({ time: point.time as UTCTimestamp, value: point.value })),
    );
    if (points.length > 0 && fittedKey.current !== resetKey) {
      chart.current?.timeScale().fitContent();
      fittedKey.current = resetKey;
    }
  }, [points, resetKey]);

  return <div className="chart" ref={container} />;
}
