import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type BusinessDay,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";

import type { KlineResponse } from "@/api/diagnose";

export interface KlineBarInfo {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  changePct: number | null;
  amount: number | null;
}

function fmtPrice(v: number): string {
  return v.toFixed(2);
}

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtAmount(v: number | null): string {
  if (v == null || v <= 0) return "—";
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return `${v.toFixed(0)}元`;
}

function buildBarDetailsMap(candles: KlineResponse["candles"]): Map<string, KlineBarInfo> {
  const map = new Map<string, KlineBarInfo>();
  for (const c of sortUniqueByTime(candles ?? [])) {
    const date = normDate(c.time);
    map.set(date, {
      date,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      changePct: c.change_pct ?? null,
      amount: c.amount ?? null,
    });
  }
  return map;
}

function KlineHoverPanel({ bar }: { bar: KlineBarInfo | null }) {
  if (!bar) return null;
  const chgColor =
    bar.changePct == null ? "#666" : bar.changePct >= 0 ? "#cf1322" : "#3f8600";
  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        right: 72,
        zIndex: 2,
        pointerEvents: "none",
        background: "rgba(255,255,255,0.92)",
        border: "1px solid #e8e8e8",
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: 12,
        lineHeight: 1.6,
        color: "#333",
        boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
        minWidth: 280,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 2 }}>{bar.date}</div>
      <div>
        <span style={{ marginRight: 10 }}>开 {fmtPrice(bar.open)}</span>
        <span style={{ marginRight: 10, color: "#cf1322" }}>高 {fmtPrice(bar.high)}</span>
        <span style={{ marginRight: 10, color: "#3f8600" }}>低 {fmtPrice(bar.low)}</span>
        <span style={{ color: bar.close >= bar.open ? "#cf1322" : "#3f8600" }}>
          收 {fmtPrice(bar.close)}
        </span>
      </div>
      <div>
        涨幅 <span style={{ color: chgColor, fontWeight: 600 }}>{fmtPct(bar.changePct)}</span>
        <span style={{ marginLeft: 14 }}>成交额 {fmtAmount(bar.amount)}</span>
      </div>
    </div>
  );
}

/** 统一为 YYYY-MM-DD，避免混合格式导致排序异常。 */
function normDate(t: string): string {
  const s = String(t).trim().slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return s;
  return d.toISOString().slice(0, 10);
}

function compareDate(a: string, b: string): number {
  return normDate(a).localeCompare(normDate(b));
}

function toBusinessDay(time: string): BusinessDay {
  const [y, m, d] = normDate(time).split("-").map(Number);
  return { year: y, month: m, day: d };
}

function businessDayKey(t: Time): string {
  if (typeof t === "string") return normDate(t);
  if (typeof t === "number") return new Date(t * 1000).toISOString().slice(0, 10);
  const b = t as BusinessDay;
  return `${b.year}-${String(b.month).padStart(2, "0")}-${String(b.day).padStart(2, "0")}`;
}

function filterMarkersInRange(
  markers: KlineMarker[],
  candles: CandlestickData<Time>[]
): KlineMarker[] {
  if (!candles.length) return markers;
  const first = businessDayKey(candles[0].time);
  const last = businessDayKey(candles[candles.length - 1].time);
  return markers.filter((m) => {
    const t = normDate(m.time);
    return t >= first && t <= last;
  });
}

function sortMarkers(markers: KlineMarker[]): KlineMarker[] {
  return [...markers]
    .map((m) => ({ ...m, time: normDate(m.time) }))
    .sort((a, b) => compareDate(a.time, b.time));
}

function sortUniqueByTime<T extends { time: string }>(rows: T[]): T[] {
  if (!rows?.length) return [];
  const sorted = [...rows].sort((a, b) => compareDate(a.time, b.time));
  const out: T[] = [];
  let last = "";
  for (const row of sorted) {
    const t = normDate(row.time);
    const item = { ...row, time: t };
    if (t === last && out.length > 0) {
      out[out.length - 1] = item;
    } else {
      out.push(item);
      last = t;
    }
  }
  return out;
}

function assertAscTimes(label: string, times: string[]): void {
  for (let i = 1; i < times.length; i += 1) {
    if (compareDate(times[i - 1], times[i]) > 0) {
      throw new Error(`${label} not ascending at ${i}: ${times[i - 1]} > ${times[i]}`);
    }
  }
}

export interface KlineMarker {
  time: string;
  position: "aboveBar" | "belowBar" | "inBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle" | "square";
  text?: string;
}

interface PreparedChartData {
  candles: CandlestickData<Time>[];
  volume: HistogramData<Time>[];
  ma5: LineData<Time>[];
  ma20: LineData<Time>[];
  ma60: LineData<Time>[];
  belowMarkers: SeriesMarker<Time>[];
  aboveMarkers: SeriesMarker<Time>[];
  belowMarkerLine: LineData<Time>[];
  aboveMarkerLine: LineData<Time>[];
}

const HIDDEN_LINE_OPTS = {
  color: "rgba(0,0,0,0)",
  lineWidth: 1,
  lineVisible: false,
  priceLineVisible: false,
  lastValueVisible: false,
  crosshairMarkerVisible: false,
} as const;

function buildCloseByDate(candles: CandlestickData<Time>[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const c of candles) {
    map.set(businessDayKey(c.time), c.close);
  }
  return map;
}

/** 标记挂在独立 line series 上，避免 candlestick 同系列多标记显示异常。 */
function lineDataForMarkers(
  markers: SeriesMarker<Time>[],
  closeByDate: Map<string, number>
): LineData<Time>[] {
  const seen = new Set<string>();
  const out: LineData<Time>[] = [];
  for (const m of markers) {
    const key = businessDayKey(m.time);
    if (seen.has(key)) continue;
    const close = closeByDate.get(key);
    if (close == null) continue;
    seen.add(key);
    out.push({ time: m.time, value: close });
  }
  out.sort((a, b) => compareDate(businessDayKey(a.time), businessDayKey(b.time)));
  return out;
}

function prepareChartData(data: KlineResponse, markers?: KlineMarker[]): PreparedChartData {
  const candlesRaw = sortUniqueByTime(data.candles ?? []);
  const volumeRaw = sortUniqueByTime(data.volume ?? []);
  const ma5Raw = sortUniqueByTime(data.ma5 ?? []);
  const ma20Raw = sortUniqueByTime(data.ma20 ?? []);
  const ma60Raw = sortUniqueByTime(data.ma60 ?? []);
  const markersRaw = sortMarkers(markers ?? []);

  const candleTimes = candlesRaw.map((c) => c.time);
  assertAscTimes("candles", candleTimes);

  const candles: CandlestickData<Time>[] = candlesRaw.map((c) => ({
    time: toBusinessDay(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
  const volume: HistogramData<Time>[] = volumeRaw.map((v) => ({
    time: toBusinessDay(v.time),
    value: v.value,
    color: v.color,
  }));
  const ma5: LineData<Time>[] = ma5Raw.map((p) => ({
    time: toBusinessDay(p.time),
    value: p.value,
  }));
  const ma20: LineData<Time>[] = ma20Raw.map((p) => ({
    time: toBusinessDay(p.time),
    value: p.value,
  }));
  const ma60: LineData<Time>[] = ma60Raw.map((p) => ({
    time: toBusinessDay(p.time),
    value: p.value,
  }));
  const markerList: SeriesMarker<Time>[] = filterMarkersInRange(markersRaw, candlesRaw).map((mk) => ({
    time: toBusinessDay(mk.time),
    position: mk.position,
    color: mk.color,
    shape: mk.shape,
    text: mk.text,
  }));
  const belowMarkers = markerList.filter((m) => m.position === "belowBar");
  const aboveMarkers = markerList.filter((m) => m.position !== "belowBar");
  const closeByDate = buildCloseByDate(candles);

  return {
    candles,
    volume,
    ma5,
    ma20,
    ma60,
    belowMarkers,
    aboveMarkers,
    belowMarkerLine: lineDataForMarkers(belowMarkers, closeByDate),
    aboveMarkerLine: lineDataForMarkers(aboveMarkers, closeByDate),
  };
}

interface Props {
  data?: KlineResponse;
  markers?: KlineMarker[];
  height?: number;
  /** 初始视口以该交易日为中心 */
  focusDate?: string;
  /** 视口可见 K 线根数（默认 100） */
  visibleBars?: number;
}

function applyFocusRange(
  chart: IChartApi,
  candles: CandlestickData<Time>[],
  focusDate: string,
  visibleBars: number
): void {
  const key = normDate(focusDate);
  const centerIdx = candles.findIndex((c) => businessDayKey(c.time) === key);
  if (centerIdx < 0) {
    chart.timeScale().fitContent();
    return;
  }
  const half = Math.max(24, Math.floor(visibleBars / 2));
  let from = centerIdx - half;
  let to = centerIdx + half;
  if (from < 0) {
    to += -from;
    from = 0;
  }
  if (to > candles.length - 1) {
    from = Math.max(0, from - (to - (candles.length - 1)));
    to = candles.length - 1;
  }
  chart.timeScale().setVisibleLogicalRange({ from, to });
}

function syncChartLayout(
  chart: IChartApi,
  container: HTMLDivElement,
  chartHeight: number,
  prepared: PreparedChartData,
  focus?: string,
  bars = 100
): boolean {
  const width = container.clientWidth;
  if (width <= 0) return false;
  chart.applyOptions({ width, height: chartHeight });
  if (focus) {
    applyFocusRange(chart, prepared.candles, focus, bars);
  } else {
    chart.timeScale().fitContent();
  }
  return true;
}

export default function KlineChart({
  data,
  markers,
  height = 480,
  focusDate,
  visibleBars = 100,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ma5Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma60Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const belowMarkerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const aboveMarkerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const preparedRef = useRef<PreparedChartData | null>(null);
  const focusDateRef = useRef(focusDate);
  const visibleBarsRef = useRef(visibleBars);
  const [chartReady, setChartReady] = useState(false);
  const [hoverBar, setHoverBar] = useState<KlineBarInfo | null>(null);

  useEffect(() => {
    focusDateRef.current = focusDate;
  }, [focusDate]);

  useEffect(() => {
    visibleBarsRef.current = visibleBars;
  }, [visibleBars]);

  const prepared = useMemo(() => {
    if (!data) return null;
    try {
      return prepareChartData(data, markers);
    } catch (e) {
      console.error("[KlineChart] prepare data failed", e, data);
      return null;
    }
  }, [data, markers]);

  const barDetails = useMemo(
    () => (data?.candles ? buildBarDetailsMap(data.candles) : new Map<string, KlineBarInfo>()),
    [data?.candles]
  );

  useEffect(() => {
    const lastDate = [...barDetails.keys()].sort().at(-1);
    setHoverBar(lastDate ? barDetails.get(lastDate) ?? null : null);
  }, [barDetails]);

  useEffect(() => {
    preparedRef.current = prepared;
  }, [prepared]);

  const layoutChart = useCallback(() => {
    const container = containerRef.current;
    const chart = chartRef.current;
    const dataReady = preparedRef.current;
    if (!container || !chart || !dataReady) return;
    syncChartLayout(
      chart,
      container,
      height,
      dataReady,
      focusDateRef.current,
      visibleBarsRef.current
    );
  }, [height]);

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const chart = createChart(container, {
      width: Math.max(container.clientWidth, 1),
      height,
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#333" },
      grid: {
        vertLines: { color: "#f0f0f0" },
        horzLines: { color: "#f0f0f0" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        borderColor: "#d1d5db",
        rightOffset: 6,
        fixLeftEdge: true,
        fixRightEdge: true,
        minBarSpacing: 0.5,
      },
      rightPriceScale: { borderColor: "#d1d5db" },
    });
    chartRef.current = chart;

    candleRef.current = chart.addCandlestickSeries({
      upColor: "#ef5350",
      downColor: "#26a69a",
      borderVisible: false,
      wickUpColor: "#ef5350",
      wickDownColor: "#26a69a",
    });

    volumeRef.current = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      color: "#bdbdbd",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    ma5Ref.current = chart.addLineSeries({
      color: "#fb8c00",
      lineWidth: 1,
      priceLineVisible: false,
    });
    ma20Ref.current = chart.addLineSeries({
      color: "#7e57c2",
      lineWidth: 1,
      priceLineVisible: false,
    });
    ma60Ref.current = chart.addLineSeries({
      color: "#0288d1",
      lineWidth: 1,
      priceLineVisible: false,
    });

    belowMarkerRef.current = chart.addLineSeries(HIDDEN_LINE_OPTS);
    aboveMarkerRef.current = chart.addLineSeries(HIDDEN_LINE_OPTS);

    setChartReady(true);

    const ro = new ResizeObserver(() => layoutChart());
    ro.observe(container);
    window.addEventListener("resize", layoutChart);

    return () => {
      setChartReady(false);
      ro.disconnect();
      window.removeEventListener("resize", layoutChart);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      ma5Ref.current = null;
      ma20Ref.current = null;
      ma60Ref.current = null;
      belowMarkerRef.current = null;
      aboveMarkerRef.current = null;
    };
  }, [height, layoutChart]);

  useEffect(() => {
    if (!chartReady || !prepared || !candleRef.current) return;
    try {
      candleRef.current.setData(prepared.candles);
      volumeRef.current?.setData(prepared.volume);
      ma5Ref.current?.setData(prepared.ma5);
      ma20Ref.current?.setData(prepared.ma20);
      ma60Ref.current?.setData(prepared.ma60);
      candleRef.current.setMarkers([]);
      belowMarkerRef.current?.setData(prepared.belowMarkerLine);
      belowMarkerRef.current?.setMarkers(prepared.belowMarkers);
      aboveMarkerRef.current?.setData(prepared.aboveMarkerLine);
      aboveMarkerRef.current?.setMarkers(prepared.aboveMarkers);
      // Modal 二次打开时容器宽度常为 0，需在布局稳定后重算
      layoutChart();
      requestAnimationFrame(() => {
        layoutChart();
        requestAnimationFrame(layoutChart);
      });
    } catch (e) {
      console.error("[KlineChart] setData failed", e, prepared);
    }
  }, [chartReady, prepared, layoutChart]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chartReady || !chart || barDetails.size === 0) return;

    const lastDate = [...barDetails.keys()].sort().at(-1);
    const lastBar = lastDate ? barDetails.get(lastDate) ?? null : null;

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (!param.time) {
        setHoverBar(lastBar);
        return;
      }
      const key = businessDayKey(param.time);
      setHoverBar(barDetails.get(key) ?? lastBar);
    };

    chart.subscribeCrosshairMove(onCrosshairMove);
    return () => chart.unsubscribeCrosshairMove(onCrosshairMove);
  }, [chartReady, barDetails]);

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      <div ref={containerRef} style={{ width: "100%", height }} />
      <KlineHoverPanel bar={hoverBar} />
    </div>
  );
}
