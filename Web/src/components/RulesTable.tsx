import { Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { DiagnoseRule } from "@/api/diagnose";

const { Text } = Typography;

const STATUS_COLOR: Record<DiagnoseRule["status"], string> = {
  pass: "green",
  fail: "red",
  warn: "orange",
  skip: "default",
};

const STATUS_LABEL: Record<DiagnoseRule["status"], string> = {
  pass: "通过",
  fail: "未通过",
  warn: "警告",
  skip: "跳过",
};

interface Props {
  rules: DiagnoseRule[];
}

const fmt = (v: unknown): string => {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") return Number(v).toString();
  if (Array.isArray(v)) return v.map(fmt).join(" ~ ");
  return String(v);
};

export default function RulesTable({ rules }: Props) {
  const columns: ColumnsType<DiagnoseRule> = [
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      align: "center",
      render: (s: DiagnoseRule["status"]) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s]}</Tag>,
    },
    { title: "规则", dataIndex: "name", width: 220 },
    {
      title: "实际值",
      dataIndex: "value",
      width: 240,
      render: (v: unknown) => <Text code>{fmt(v)}</Text>,
    },
    {
      title: "阈值",
      dataIndex: "threshold",
      width: 140,
      render: (v: unknown) => <Text type="secondary">{fmt(v)}</Text>,
    },
    {
      title: "说明",
      dataIndex: "note",
      render: (v: string) => v || "—",
    },
  ];

  return (
    <Table<DiagnoseRule>
      rowKey={(r) => `${r.name}-${String(r.value)}`}
      dataSource={rules}
      columns={columns}
      pagination={false}
      size="small"
      bordered
    />
  );
}
