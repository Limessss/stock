import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

import type { MonthlyReturn } from "@/api/backtest";

interface Props {
  monthly: MonthlyReturn[];
  height?: number;
}

const MONTH_LABELS = [
  "1月", "2月", "3月", "4月", "5月", "6月",
  "7月", "8月", "9月", "10月", "11月", "12月",
];

export default function MonthlyHeatmap({ monthly, height = 280 }: Props) {
  const option = useMemo(() => {
    if (!monthly.length) return null;
    const years = Array.from(new Set(monthly.map((m) => m.year))).sort();
    const data = monthly.map((m) => [m.month - 1, years.indexOf(m.year), Number(m.return_pct.toFixed(2))]);
    const values = monthly.map((m) => m.return_pct);
    const absMax = Math.max(...values.map(Math.abs), 1);

    return {
      tooltip: {
        position: "top",
        formatter: (p: { data: [number, number, number] }) => {
          const [mIdx, yIdx, v] = p.data;
          return `${years[yIdx]}-${String(mIdx + 1).padStart(2, "0")}<br/>收益 <b>${v.toFixed(2)}%</b>`;
        },
      },
      grid: { top: 20, bottom: 30, left: 60, right: 30 },
      xAxis: {
        type: "category",
        data: MONTH_LABELS,
        splitArea: { show: true },
      },
      yAxis: {
        type: "category",
        data: years.map(String),
        splitArea: { show: true },
      },
      visualMap: {
        min: -absMax,
        max: absMax,
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        inRange: {
          color: ["#cf1322", "#fff7e6", "#3f8600"],
        },
        text: ["+%", "-%"],
      },
      series: [{
        name: "月度收益",
        type: "heatmap",
        data,
        label: {
          show: true,
          formatter: (p: { data: [number, number, number] }) => {
            const v = p.data[2];
            return v ? `${v >= 0 ? "+" : ""}${v.toFixed(1)}` : "";
          },
          fontSize: 10,
        },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.3)" },
        },
      }],
    };
  }, [monthly]);

  if (!option) return <div style={{ color: "#999", padding: 16 }}>无月度数据</div>;
  return <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />;
}
