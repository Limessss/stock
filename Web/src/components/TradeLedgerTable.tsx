import { Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { LedgerRow } from "@/api/backtest";
import type { StockKlineTarget } from "@/components/StockKlineModal";

const { Text } = Typography;

interface Props {
  rows: LedgerRow[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onStockClick?: (stock: StockKlineTarget) => void;
}

function fmtMoney(v: number): string {
  return v.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function TradeLedgerTable({
  rows,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onStockClick,
}: Props) {
  const openStock = (r: LedgerRow) => {
    onStockClick?.({
      code: r.code,
      name: r.name,
      signalDate: r.signal_date,
      buyDate: r.action === "buy" ? r.date : r.buy_date ?? undefined,
      sellDate: r.action === "sell" ? r.date : undefined,
    });
  };

  const columns: ColumnsType<LedgerRow> = [
    {
      title: "日期",
      dataIndex: "date",
      width: 110,
      fixed: "left",
    },
    {
      title: "动作",
      dataIndex: "action",
      width: 72,
      fixed: "left",
      render: (v: string) =>
        v === "buy" ? (
          <Tag color="red">买入</Tag>
        ) : (
          <Tag color="green">卖出</Tag>
        ),
    },
    {
      title: "代码",
      dataIndex: "code",
      width: 100,
      render: (v: string, r) =>
        onStockClick ? (
          <a
            onClick={(e) => {
              e.stopPropagation();
              openStock(r);
            }}
          >
            {v}
          </a>
        ) : (
          v
        ),
    },
    {
      title: "名称",
      dataIndex: "name",
      width: 100,
      render: (v: string, r) =>
        onStockClick && v ? (
          <a
            onClick={(e) => {
              e.stopPropagation();
              openStock(r);
            }}
          >
            {v}
          </a>
        ) : (
          v || <Text type="secondary">—</Text>
        ),
    },
    {
      title: "价格",
      dataIndex: "price",
      width: 90,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "数量(股)",
      dataIndex: "quantity",
      width: 100,
      align: "right",
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: "金额(元)",
      dataIndex: "amount",
      width: 120,
      align: "right",
      render: (v: number) => fmtMoney(v),
    },
    {
      title: "盈利(元)",
      dataIndex: "profit_amount",
      width: 110,
      align: "right",
      render: (v: number | null) =>
        v == null ? (
          <Text type="secondary">—</Text>
        ) : (
          <Text style={{ color: v >= 0 ? "#cf1322" : "#3f8600", fontWeight: 600 }}>
            {v >= 0 ? "+" : ""}
            {fmtMoney(v)}
          </Text>
        ),
    },
    {
      title: "信号日",
      dataIndex: "signal_date",
      width: 110,
    },
    {
      title: "备注",
      dataIndex: "sell_reason",
      width: 160,
      render: (v: string | null) => (v ? <Text type="secondary">{v}</Text> : "—"),
    },
  ];

  return (
    <Table<LedgerRow>
      rowKey={(r) => `${r.date}-${r.action}-${r.code}-${r.signal_date}`}
      dataSource={rows}
      columns={columns}
      loading={loading}
      size="small"
      scroll={{ x: 1100 }}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: true,
        pageSizeOptions: ["50", "100", "200", "500"],
        onChange: onPageChange,
      }}
    />
  );
}
