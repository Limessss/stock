import { useMemo, useState } from "react";
import { Button, Input, Popconfirm, Select, Space, Table, Tag, Typography } from "@/components/ui";
import type { ColumnsType } from "@/components/ui";
import { DeleteOutlined, EyeOutlined, SearchOutlined } from "@/components/ui/icons";

import type { BacktestTask } from "@/api/backtest";
import type { StrategyInfo } from "@/api/scan";
import { formatBeijingTime, parseApiTime } from "@/lib/dayjsSetup";

const { Text } = Typography;

const STATUS_TAG: Record<BacktestTask["status"], { color: string; label: string }> = {
  pending: { color: "default", label: "排队中" },
  running: { color: "processing", label: "运行中" },
  done: { color: "success", label: "已完成" },
  error: { color: "error", label: "失败" },
  cancelled: { color: "warning", label: "已取消" },
};

const STATUS_OPTIONS = Object.entries(STATUS_TAG).map(([value, { label }]) => ({
  value,
  label,
}));

function num(v: number | null | undefined, fallback = -Infinity): number {
  return v == null || Number.isNaN(v) ? fallback : v;
}

function MetricCell({
  value,
  suffix = "",
  color,
}: {
  value: number | null | undefined;
  suffix?: string;
  color?: string;
}) {
  if (value == null) return <Text type="secondary">—</Text>;
  return (
    <Text style={{ color }}>
      {suffix === "profit" && value >= 0 ? "+" : ""}
      {suffix === "profit"
        ? value.toLocaleString(undefined, { maximumFractionDigits: 0 })
        : value.toFixed(suffix === "pct1" ? 1 : 2)}
      {suffix === "pct" || suffix === "pct1" ? "%" : ""}
    </Text>
  );
}

interface Props {
  tasks: BacktestTask[];
  strategies: StrategyInfo[];
  loading?: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  deletingId?: string;
}

export default function BacktestHistoryTable({
  tasks,
  strategies,
  loading,
  onSelect,
  onDelete,
  deletingId,
}: Props) {
  const [search, setSearch] = useState("");
  const [strategyFilter, setStrategyFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<BacktestTask["status"] | undefined>();

  const strategyMap = useMemo(
    () => new Map(strategies.map((s) => [s.name, s.label])),
    [strategies]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return tasks.filter((t) => {
      if (strategyFilter && t.strategy_name !== strategyFilter) return false;
      if (statusFilter && t.status !== statusFilter) return false;
      if (!q) return true;
      const name = (t.name ?? "").toLowerCase();
      return name.includes(q) || t.id.toLowerCase().includes(q);
    });
  }, [tasks, search, strategyFilter, statusFilter]);

  const columns: ColumnsType<BacktestTask> = [
    {
      title: "任务名",
      dataIndex: "name",
      width: 140,
      fixed: "left",
      ellipsis: true,
      render: (_, r) => (
        <div>
          <Text strong>{r.name || r.id.slice(0, 8)}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>
            {r.id.slice(0, 8)}…
          </Text>
        </div>
      ),
      sorter: (a, b) => (a.name ?? a.id).localeCompare(b.name ?? b.id),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 88,
      render: (s: BacktestTask["status"]) => (
        <Tag color={STATUS_TAG[s].color}>{STATUS_TAG[s].label}</Tag>
      ),
    },
    {
      title: "策略",
      dataIndex: "strategy_name",
      width: 100,
      ellipsis: true,
      render: (name: string) => <Tag color="blue">{strategyMap.get(name) ?? name}</Tag>,
    },
    {
      title: "回测区间",
      width: 190,
      render: (_, r) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {r.start_date} → {r.end_date}
        </Text>
      ),
      sorter: (a, b) => a.start_date.localeCompare(b.start_date),
    },
    {
      title: "笔数",
      dataIndex: "trade_count",
      width: 72,
      align: "right",
      sorter: (a, b) => a.trade_count - b.trade_count,
    },
    {
      title: "胜率",
      width: 80,
      align: "right",
      render: (_, r) => (
        <MetricCell
          value={r.summary?.win_rate}
          suffix="pct1"
          color={
            r.summary?.win_rate != null
              ? r.summary.win_rate >= 50
                ? "#3f8600"
                : "#cf1322"
              : undefined
          }
        />
      ),
      sorter: (a, b) => num(a.summary?.win_rate) - num(b.summary?.win_rate),
    },
    {
      title: "均收益",
      width: 88,
      align: "right",
      render: (_, r) => (
        <MetricCell
          value={r.summary?.avg_return}
          suffix="pct"
          color={
            r.summary?.avg_return != null
              ? r.summary.avg_return >= 0
                ? "#3f8600"
                : "#cf1322"
              : undefined
          }
        />
      ),
      sorter: (a, b) => num(a.summary?.avg_return) - num(b.summary?.avg_return),
    },
    {
      title: "累计盈利",
      width: 110,
      align: "right",
      render: (_, r) => (
        <MetricCell
          value={r.summary?.total_profit}
          suffix="profit"
          color={
            r.summary?.total_profit != null
              ? r.summary.total_profit >= 0
                ? "#cf1322"
                : "#3f8600"
              : undefined
          }
        />
      ),
      sorter: (a, b) => num(a.summary?.total_profit) - num(b.summary?.total_profit),
    },
    {
      title: "最大回撤",
      width: 96,
      align: "right",
      render: (_, r) => (
        <MetricCell value={r.summary?.max_drawdown_pct} suffix="pct" color="#cf1322" />
      ),
      sorter: (a, b) => num(a.summary?.max_drawdown_pct) - num(b.summary?.max_drawdown_pct),
    },
    {
      title: "夏普",
      width: 72,
      align: "right",
      render: (_, r) => {
        const v = r.summary?.sharpe;
        return (
          <MetricCell
            value={v}
            color={v != null ? (v >= 1 ? "#3f8600" : v >= 0 ? "#fa8c16" : "#cf1322") : undefined}
          />
        );
      },
      sorter: (a, b) => num(a.summary?.sharpe) - num(b.summary?.sharpe),
    },
    {
      title: "耗时",
      dataIndex: "elapsed_seconds",
      width: 72,
      align: "right",
      render: (v: number | null) =>
        v != null ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {v.toFixed(1)}s
          </Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
      sorter: (a, b) => num(a.elapsed_seconds) - num(b.elapsed_seconds),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 160,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {formatBeijingTime(v, "YYYY-MM-DD HH:mm")}
        </Text>
      ),
      sorter: (a, b) =>
        parseApiTime(a.created_at).valueOf() - parseApiTime(b.created_at).valueOf(),
      defaultSortOrder: "descend",
    },
    {
      title: "操作",
      key: "actions",
      width: 96,
      fixed: "right",
      render: (_, r) => {
        const isRunning = r.status === "running" || r.status === "pending";
        return (
          <Space size={4} onClick={(e) => e.stopPropagation()}>
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => onSelect(r.id)}
            />
            <Popconfirm
              title="删除此回测记录？"
              description={
                isRunning
                  ? "任务仍在运行，删除后记录与结果将被清除，后台进程可能仍在执行。"
                  : "删除后不可恢复，关联成交数据一并清除。"
              }
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => onDelete(r.id)}
            >
              <Button
                type="link"
                danger
                size="small"
                icon={<DeleteOutlined />}
                loading={deletingId === r.id}
              />
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space wrap>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索任务名 / ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 220 }}
        />
        <Select
          allowClear
          placeholder="策略"
          value={strategyFilter}
          onChange={setStrategyFilter}
          options={strategies.map((s) => ({ label: s.label, value: s.name }))}
          style={{ width: 140 }}
        />
        <Select
          allowClear
          placeholder="状态"
          value={statusFilter}
          onChange={setStatusFilter}
          options={STATUS_OPTIONS}
          style={{ width: 120 }}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          共 {filtered.length} / {tasks.length} 条
        </Text>
      </Space>

      <Table<BacktestTask>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={filtered}
        scroll={{ x: 1300 }}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          pageSizeOptions: ["10", "20", "50"],
          showTotal: (total) => `共 ${total} 条`,
        }}
        onRow={(record) => ({
          onClick: () => onSelect(record.id),
          style: { cursor: "pointer" },
        })}
      />
    </Space>
  );
}
