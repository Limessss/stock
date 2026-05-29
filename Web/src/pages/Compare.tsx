import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Card,
  Col,
  Empty,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { SwapOutlined } from "@ant-design/icons";

import {
  getBacktest,
  getBacktestMetrics,
  listBacktestHistory,
  type BacktestSummary,
  type BacktestTask,
} from "@/api/backtest";
import { getFactorAnalysis } from "@/api/factor";
import EquityCurve from "@/components/EquityCurve";

const { Title, Text } = Typography;

const COLOR_A = "#1677ff";
const COLOR_B = "#fa541c";

interface DiffStat {
  label: string;
  unit: string;
  a: number;
  b: number;
  precision?: number;
  /** true: 越大越好；false: 越小越好；null: 无方向 */
  better?: boolean | null;
}

export default function ComparePage() {
  const [aId, setAId] = useState<string | null>(null);
  const [bId, setBId] = useState<string | null>(null);

  const historyQ = useQuery({
    queryKey: ["bt-history-compare"],
    queryFn: () => listBacktestHistory(50),
    staleTime: 30_000,
  });
  const candidates = useMemo(
    () => (historyQ.data ?? []).filter((t) => t.status === "done" && t.trade_count >= 1),
    [historyQ.data]
  );

  // 默认选最近两个
  const effA = aId ?? candidates[0]?.id ?? null;
  const effB = bId ?? candidates[1]?.id ?? null;

  const aQ = useQuery({
    queryKey: ["bt-task-cmp", effA],
    queryFn: () => getBacktest(effA!),
    enabled: !!effA,
  });
  const bQ = useQuery({
    queryKey: ["bt-task-cmp", effB],
    queryFn: () => getBacktest(effB!),
    enabled: !!effB,
  });
  const aMetricsQ = useQuery({
    queryKey: ["bt-metrics-cmp", effA],
    queryFn: () => getBacktestMetrics(effA!),
    enabled: !!effA,
  });
  const bMetricsQ = useQuery({
    queryKey: ["bt-metrics-cmp", effB],
    queryFn: () => getBacktestMetrics(effB!),
    enabled: !!effB,
  });
  const aFactorQ = useQuery({
    queryKey: ["bt-factor-cmp", effA],
    queryFn: () => getFactorAnalysis(effA!),
    enabled: !!effA,
  });
  const bFactorQ = useQuery({
    queryKey: ["bt-factor-cmp", effB],
    queryFn: () => getFactorAnalysis(effB!),
    enabled: !!effB,
  });

  const aTask = aQ.data;
  const bTask = bQ.data;

  const stats: DiffStat[] = useMemo(() => {
    const sa: BacktestSummary | undefined = aTask?.summary ?? undefined;
    const sb: BacktestSummary | undefined = bTask?.summary ?? undefined;
    if (!sa || !sb) return [];
    return [
      { label: "成交笔数", unit: "", a: sa.total_trades, b: sb.total_trades, precision: 0, better: null },
      { label: "胜率", unit: "%", a: sa.win_rate, b: sb.win_rate, precision: 2, better: true },
      { label: "平均收益", unit: "%", a: sa.avg_return, b: sb.avg_return, precision: 2, better: true },
      { label: "中位收益", unit: "%", a: sa.median_return, b: sb.median_return, precision: 2, better: true },
      { label: "大赚率(≥+20%)", unit: "%", a: sa.big_win_rate, b: sb.big_win_rate, precision: 2, better: true },
      { label: "大亏率(≤-7%)", unit: "%", a: sa.big_loss_rate, b: sb.big_loss_rate, precision: 2, better: false },
      { label: "平均持有天数", unit: "天", a: sa.avg_hold_days, b: sb.avg_hold_days, precision: 1, better: null },
      { label: "年化收益", unit: "%", a: sa.cagr_pct ?? 0, b: sb.cagr_pct ?? 0, precision: 2, better: true },
      { label: "夏普比率", unit: "", a: sa.sharpe ?? 0, b: sb.sharpe ?? 0, precision: 2, better: true },
      { label: "最大回撤", unit: "%", a: sa.max_drawdown_pct ?? 0, b: sb.max_drawdown_pct ?? 0, precision: 2, better: true /* less-negative is better; with sign already negative, "larger" wins */ },
      { label: "Calmar", unit: "", a: sa.calmar ?? 0, b: sb.calmar ?? 0, precision: 2, better: true },
    ];
  }, [aTask, bTask]);

  const icRows = useMemo(() => {
    const aFa = aFactorQ.data?.ic ?? [];
    const bFa = bFactorQ.data?.ic ?? [];
    const map = new Map<string, { label: string; a: number | null; b: number | null }>();
    for (const r of aFa) map.set(r.field, { label: r.label, a: r.ic_return, b: null });
    for (const r of bFa) {
      const e = map.get(r.field) ?? { label: r.label, a: null, b: null };
      e.b = r.ic_return;
      map.set(r.field, e);
    }
    return Array.from(map.entries()).map(([k, v]) => ({ field: k, ...v, diff: (v.b ?? 0) - (v.a ?? 0) }))
      .sort((x, y) => Math.abs(y.a ?? 0) - Math.abs(x.a ?? 0));
  }, [aFactorQ.data, bFactorQ.data]);

  return (
    <>
      <Title level={3} style={{ marginTop: 0 }}>
        <SwapOutlined /> 参数对比
      </Title>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={12}>
            <Text type="secondary">任务 A</Text>
            <TaskSelect
              value={effA}
              onChange={setAId}
              candidates={candidates}
              loading={historyQ.isLoading}
              dotColor={COLOR_A}
            />
          </Col>
          <Col span={12}>
            <Text type="secondary">任务 B</Text>
            <TaskSelect
              value={effB}
              onChange={setBId}
              candidates={candidates}
              loading={historyQ.isLoading}
              dotColor={COLOR_B}
            />
          </Col>
        </Row>
      </Card>

      {(!effA || !effB) && (
        <Alert
          type="info"
          showIcon
          message="需要至少 2 个已完成的回测任务"
          description="去『回测』页跑两轮（修改某个参数对比效果），完成后再来这里。"
        />
      )}

      {aTask && bTask && (
        <>
          <Card title="任务摘要" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={12}>
                <TaskHeader task={aTask} dotColor={COLOR_A} label="A" />
              </Col>
              <Col span={12}>
                <TaskHeader task={bTask} dotColor={COLOR_B} label="B" />
              </Col>
            </Row>
          </Card>

          <Card title="指标对比" style={{ marginBottom: 16 }}>
            <Table
              size="small"
              rowKey="label"
              dataSource={stats}
              pagination={false}
              columns={[
                { title: "指标", dataIndex: "label" },
                {
                  title: <Tag color="blue">A</Tag>,
                  render: (_: unknown, r: DiffStat) => fmt(r.a, r.precision, r.unit),
                  align: "right",
                },
                {
                  title: <Tag color="orange">B</Tag>,
                  render: (_: unknown, r: DiffStat) => fmt(r.b, r.precision, r.unit),
                  align: "right",
                },
                {
                  title: "差值 (B-A)",
                  align: "right",
                  render: (_: unknown, r: DiffStat) => {
                    const d = r.b - r.a;
                    if (Math.abs(d) < 1e-9) return <Text type="secondary">—</Text>;
                    let color: string | undefined;
                    if (r.better === true) color = d > 0 ? "#3f8600" : "#cf1322";
                    else if (r.better === false) color = d > 0 ? "#cf1322" : "#3f8600";
                    return (
                      <Text style={{ color, fontFamily: "monospace", fontWeight: 600 }}>
                        {d > 0 ? "+" : ""}
                        {fmtNum(d, r.precision)}{r.unit}
                      </Text>
                    );
                  },
                },
              ]}
            />
          </Card>

          <Card title="净值曲线（叠加）" style={{ marginBottom: 16 }}>
            {aMetricsQ.data && bMetricsQ.data ? (
              <EquityCurve
                series={[
                  { name: `A · ${aTask.name || aTask.id.slice(0, 8)}`, color: COLOR_A, equity: aMetricsQ.data.equity_curve },
                  { name: `B · ${bTask.name || bTask.id.slice(0, 8)}`, color: COLOR_B, equity: bMetricsQ.data.equity_curve },
                ]}
                height={360}
              />
            ) : (
              <div style={{ color: "#999", padding: 16 }}>加载净值数据中...</div>
            )}
          </Card>

          <Card title="IC 对照">
            {icRows.length > 0 ? (
              <Table
                size="small"
                rowKey="field"
                dataSource={icRows}
                pagination={false}
                columns={[
                  { title: "因子", dataIndex: "label" },
                  { title: "字段", dataIndex: "field", render: (v: string) => <Text code>{v}</Text> },
                  { title: <Tag color="blue">A · IC</Tag>, dataIndex: "a", render: (v: number | null) => <ICCell value={v} />, align: "right" },
                  { title: <Tag color="orange">B · IC</Tag>, dataIndex: "b", render: (v: number | null) => <ICCell value={v} />, align: "right" },
                  {
                    title: "Δ |IC|",
                    align: "right",
                    render: (_: unknown, r: { a: number | null; b: number | null }) => {
                      const a = Math.abs(r.a ?? 0);
                      const b = Math.abs(r.b ?? 0);
                      const d = b - a;
                      return (
                        <Text style={{ color: d > 0 ? "#3f8600" : d < 0 ? "#cf1322" : undefined }}>
                          {d > 0 ? "+" : ""}
                          {d.toFixed(4)}
                        </Text>
                      );
                    },
                  },
                ]}
              />
            ) : (
              <Empty description="无 IC 数据" />
            )}
          </Card>
        </>
      )}
    </>
  );
}

function TaskSelect({
  value,
  onChange,
  candidates,
  loading,
  dotColor,
}: {
  value: string | null;
  onChange: (id: string) => void;
  candidates: BacktestTask[];
  loading: boolean;
  dotColor: string;
}) {
  return (
    <Select
      value={value ?? undefined}
      onChange={onChange}
      loading={loading}
      style={{ width: "100%" }}
      placeholder="选择回测任务"
      optionLabelProp="label"
    >
      {candidates.map((t) => (
        <Select.Option
          key={t.id}
          value={t.id}
          label={
            <>
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: dotColor, marginRight: 8 }} />
              {t.name || t.id.slice(0, 8)} · {t.trade_count}笔
            </>
          }
        >
          <Space>
            <Text strong>{t.name || t.id.slice(0, 8)}</Text>
            <Tag color="blue">{t.trade_count} 笔</Tag>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {t.start_date} → {t.end_date}
            </Text>
            {t.summary && (
              <Text style={{ color: t.summary.win_rate >= 50 ? "#3f8600" : "#cf1322", fontSize: 11 }}>
                胜率 {t.summary.win_rate.toFixed(1)}%
              </Text>
            )}
          </Space>
        </Select.Option>
      ))}
    </Select>
  );
}

function TaskHeader({
  task,
  dotColor,
  label,
}: {
  task: { id: string; name: string | null; strategy_name: string; start_date: string; end_date: string; take_profit: number; stop_loss: number; max_hold: number; split_tp: number | null };
  dotColor: string;
  label: string;
}) {
  return (
    <Space direction="vertical" size={4}>
      <Space>
        <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: dotColor }} />
        <Text strong>{label}</Text>
        <Text>{task.name || task.id.slice(0, 8)}</Text>
        <Text type="secondary" style={{ fontSize: 11 }}>{task.id}</Text>
      </Space>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {task.start_date} → {task.end_date} · 策略 {task.strategy_name}
      </Text>
      <Space size={12} style={{ fontSize: 12 }}>
        <Text>止盈 +{(task.take_profit * 100).toFixed(0)}%</Text>
        <Text>止损 -{(task.stop_loss * 100).toFixed(0)}%</Text>
        <Text>最长持 {task.max_hold} 日</Text>
        {task.split_tp != null && <Text>分批 +{(task.split_tp * 100).toFixed(0)}%</Text>}
      </Space>
    </Space>
  );
}

function fmt(v: number, precision = 2, unit = ""): ReactNode {
  return (
    <Text style={{ fontFamily: "monospace" }}>
      {fmtNum(v, precision)}
      {unit}
    </Text>
  );
}

function fmtNum(v: number, precision = 2): string {
  if (precision === 0) return Math.round(v).toString();
  return v.toFixed(precision);
}

function ICCell({ value }: { value: number | null }) {
  if (value == null || isNaN(value)) return <Text type="secondary">—</Text>;
  const abs = Math.abs(value);
  let color = "#999";
  if (abs >= 0.1) color = value > 0 ? "#3f8600" : "#cf1322";
  else if (abs >= 0.05) color = value > 0 ? "#52c41a" : "#fa541c";
  return (
    <Text style={{ color, fontFamily: "monospace", fontWeight: 600 }}>
      {value > 0 ? "+" : ""}
      {value.toFixed(4)}
    </Text>
  );
}
