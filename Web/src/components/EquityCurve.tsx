import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

import type { BacktestTrade, EquityPoint } from "@/api/backtest";

export interface EquitySeries {
  name: string;
  color?: string;
  equity?: EquityPoint[];
  trades?: BacktestTrade[];
}

interface Props {
  /** 优先使用后端返回的真实净值曲线（每日组合 nav）。 */
  equity?: EquityPoint[];
  /** 兼容老调用：传入 trades 时按 sell_date 累加 return_pct（粗略累计）。 */
  trades?: BacktestTrade[];
  /** 多条曲线叠加（compare 页用）。指定时忽略 equity/trades。 */
  series?: EquitySeries[];
  height?: number;
}

interface ResolvedSeries {
  name: string;
  color: string;
  data: { date: string; value: number }[];
}

const PALETTE = ["#1677ff", "#fa541c", "#52c41a", "#722ed1", "#fa8c16"];

function resolveOne(name: string, color: string, eq?: EquityPoint[], tr?: BacktestTrade[]): ResolvedSeries {
  const data: { date: string; value: number }[] = [];
  if (eq && eq.length > 0) {
    for (const p of eq) data.push({ date: p.date, value: Number(((p.nav - 1) * 100).toFixed(2)) });
  } else if (tr && tr.length > 0) {
    const sorted = [...tr].sort((a, b) => a.sell_date.localeCompare(b.sell_date));
    let cum = 0;
    for (const t of sorted) {
      cum += t.return_pct;
      data.push({ date: t.sell_date, value: Number(cum.toFixed(2)) });
    }
  }
  return { name, color, data };
}

export default function EquityCurve({ equity, trades, series, height = 320 }: Props) {
  const option = useMemo(() => {
    let resolved: ResolvedSeries[];
    if (series && series.length > 0) {
      resolved = series.map((s, i) =>
        resolveOne(s.name, s.color ?? PALETTE[i % PALETTE.length], s.equity, s.trades)
      );
    } else {
      const r = resolveOne(
        equity && equity.length > 0 ? "组合净值（等权）" : "累计单笔收益",
        PALETTE[0],
        equity,
        trades
      );
      resolved = [r];
    }
    resolved = resolved.filter((r) => r.data.length > 0);
    if (resolved.length === 0) return null;

    const xSet = new Set<string>();
    for (const r of resolved) for (const p of r.data) xSet.add(p.date);
    const xArr = Array.from(xSet).sort();

    const echartsSeries = resolved.map((r) => {
      const lookup = new Map(r.data.map((p) => [p.date, p.value]));
      let lastVal: number | null = null;
      const arr = xArr.map((d) => {
        if (lookup.has(d)) lastVal = lookup.get(d)!;
        return lastVal;
      });
      return {
        name: r.name,
        type: "line" as const,
        showSymbol: false,
        areaStyle: resolved.length === 1 ? { opacity: 0.15 } : undefined,
        lineStyle: { width: 2 },
        itemStyle: { color: r.color },
        data: arr,
        connectNulls: true,
      };
    });

    return {
      tooltip: { trigger: "axis" },
      legend: resolved.length > 1 ? { top: 0, right: 16 } : undefined,
      grid: { left: 50, right: 30, bottom: 50, top: resolved.length > 1 ? 30 : 20 },
      xAxis: { type: "category", data: xArr, axisLabel: { rotate: 30 } },
      yAxis: { type: "value", axisLabel: { formatter: "{value} %" } },
      dataZoom: [
        { type: "inside" },
        { type: "slider", height: 18, bottom: 4 },
      ],
      series: echartsSeries,
    };
  }, [equity, trades, series]);

  if (!option) return <div style={{ color: "#999", padding: 16 }}>无成交记录</div>;
  return <ReactECharts option={option} style={{ height }} notMerge />;
}
