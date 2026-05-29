import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

import type { FactorQuantile } from "@/api/factor";

interface Props {
  factors: FactorQuantile[];
  /** 数值字段：mean / win_rate / big_win_rate */
  metric?: "mean" | "win_rate" | "big_win_rate";
  height?: number;
}

const METRIC_LABEL: Record<NonNullable<Props["metric"]>, string> = {
  mean: "平均收益 (%)",
  win_rate: "胜率 (%)",
  big_win_rate: "大赚率 (%)",
};

export default function FactorQuantileHeatmap({
  factors,
  metric = "mean",
  height = 480,
}: Props) {
  const option = useMemo(() => {
    if (!factors.length) return null;
    // 收集所有可能出现的 quantile labels（一般 Q1..Q5；空值不绘）
    const qSet = new Set<string>();
    for (const f of factors) for (const q of f.quantiles) qSet.add(q.quantile);
    const xCats = Array.from(qSet).sort();
    const yCats = factors.map((f) => f.label);

    type Cell = [number, number, number, number]; // [x, y, value, count]
    const data: Cell[] = [];
    for (let yIdx = 0; yIdx < factors.length; yIdx++) {
      const f = factors[yIdx];
      for (const q of f.quantiles) {
        const xIdx = xCats.indexOf(q.quantile);
        const v = q[metric];
        data.push([xIdx, yIdx, Number(v.toFixed(2)), q.count]);
      }
    }
    const values = data.map((d) => d[2]);
    const absMax = Math.max(...values.map(Math.abs), 1);
    const isMean = metric === "mean";

    return {
      tooltip: {
        position: "top",
        formatter: (p: { data: Cell }) => {
          const [xIdx, yIdx, v, cnt] = p.data;
          const f = factors[yIdx];
          const q = f.quantiles[xIdx];
          if (!q) return "";
          return (
            `<b>${f.label}</b> · ${q.quantile}<br/>` +
            `${METRIC_LABEL[metric]}: <b>${v.toFixed(2)}</b><br/>` +
            `笔数: ${cnt}<br/>` +
            `中位收益: ${q.median.toFixed(2)}%<br/>` +
            `胜率: ${q.win_rate.toFixed(1)}%`
          );
        },
      },
      grid: { top: 30, bottom: 70, left: 130, right: 30 },
      xAxis: { type: "category", data: xCats, position: "top", splitArea: { show: true } },
      yAxis: {
        type: "category",
        data: yCats,
        inverse: true,
        splitArea: { show: true },
        axisLabel: { fontSize: 11 },
      },
      visualMap: {
        min: isMean ? -absMax : 0,
        max: isMean ? absMax : 100,
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 6,
        inRange: {
          color: isMean
            ? ["#cf1322", "#fff7e6", "#3f8600"]
            : ["#fff7e6", "#fa8c16", "#3f8600"],
        },
        text: isMean ? ["+", "-"] : ["高", "低"],
      },
      series: [{
        name: METRIC_LABEL[metric],
        type: "heatmap",
        data,
        label: {
          show: true,
          formatter: (p: { data: Cell }) => {
            const v = p.data[2];
            return v == null ? "" : (isMean && v > 0 ? "+" : "") + v.toFixed(1);
          },
          fontSize: 10,
        },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.3)" },
        },
      }],
    };
  }, [factors, metric]);

  if (!option) return <div style={{ color: "#999", padding: 16 }}>无数据</div>;
  return <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />;
}
