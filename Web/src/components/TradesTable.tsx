import { Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { BacktestTrade } from "@/api/backtest";
import type { StockKlineTarget } from "@/components/StockKlineModal";

const { Text } = Typography;

interface Props {
  rows: BacktestTrade[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onStockClick?: (stock: StockKlineTarget) => void;
}

const TIER_COLOR: Record<string, string> = {
  A: "magenta",
  B: "red",
  C: "orange",
  D: "default",
};

function fmtMoney(v: number): string {
  return v.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function TradesTable({
  rows,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onStockClick,
}: Props) {
  const openStock = (r: BacktestTrade) => {
    onStockClick?.({
      code: r.code,
      name: r.name,
      signalDate: r.signal_date,
      buyDate: r.buy_date,
      sellDate: r.sell_date,
    });
  };

  const columns: ColumnsType<BacktestTrade> = [
    {
      title: "代码",
      dataIndex: "code",
      width: 100,
      fixed: "left",
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
      width: 110,
      fixed: "left",
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
      title: "信号日",
      dataIndex: "signal_date",
      width: 110,
      fixed: "left",
    },
    {
      title: "板块",
      dataIndex: "market",
      width: 80,
    },
    {
      title: "等级",
      dataIndex: "tier",
      width: 70,
      align: "center",
      render: (t: string) => <Tag color={TIER_COLOR[t]}>{t}</Tag>,
    },
    {
      title: "评分",
      dataIndex: "score",
      width: 90,
      align: "right",
      sorter: (a, b) => a.score - b.score,
      defaultSortOrder: "descend",
      render: (v: number) => <Text strong>{v.toFixed(2)}</Text>,
    },
    {
      title: "买入日",
      dataIndex: "buy_date",
      width: 110,
    },
    {
      title: "买价",
      dataIndex: "buy_price",
      width: 80,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "数量",
      dataIndex: "quantity",
      width: 90,
      align: "right",
      render: (v: number) => (v > 0 ? v.toLocaleString() : "—"),
    },
    {
      title: "买入金额",
      dataIndex: "buy_amount",
      width: 110,
      align: "right",
      render: (v: number) => (v > 0 ? fmtMoney(v) : "—"),
    },
    {
      title: "卖出日",
      dataIndex: "sell_date",
      width: 110,
    },
    {
      title: "卖价",
      dataIndex: "sell_price",
      width: 80,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "卖出金额",
      dataIndex: "sell_amount",
      width: 110,
      align: "right",
      render: (v: number) => (v > 0 ? fmtMoney(v) : "—"),
    },
    {
      title: "盈利(元)",
      dataIndex: "profit_amount",
      width: 110,
      align: "right",
      sorter: (a, b) => a.profit_amount - b.profit_amount,
      render: (v: number, r) =>
        r.quantity <= 0 ? (
          <Text type="secondary">—</Text>
        ) : (
          <Text style={{ color: v >= 0 ? "#cf1322" : "#3f8600", fontWeight: 600 }}>
            {v >= 0 ? "+" : ""}
            {fmtMoney(v)}
          </Text>
        ),
    },
    {
      title: "收益%",
      dataIndex: "return_pct",
      width: 90,
      align: "right",
      sorter: (a, b) => a.return_pct - b.return_pct,
      render: (v: number) => (
        <Text style={{ color: v > 0 ? "#cf1322" : "#3f8600", fontWeight: 600 }}>
          {v > 0 ? "+" : ""}
          {v.toFixed(2)}
        </Text>
      ),
    },
    {
      title: "持有",
      dataIndex: "hold_days",
      width: 70,
      align: "right",
      render: (v: number) => `${v}d`,
    },
    {
      title: "卖出原因",
      dataIndex: "sell_reason",
      width: 160,
      render: (v: string) => <Text type="secondary">{v}</Text>,
    },
    {
      title: "最大上行%",
      dataIndex: "max_up_pct",
      width: 100,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "最大下行%",
      dataIndex: "max_dn_pct",
      width: 100,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "突破%",
      dataIndex: "breakout_pct",
      width: 80,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "量比",
      dataIndex: "vol_ratio",
      width: 70,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "MACD",
      dataIndex: "macd",
      width: 90,
      align: "right",
      render: (v: number) => v.toFixed(3),
    },
  ];

  return (
    <Table<BacktestTrade>
      rowKey={(r) => `${r.code}-${r.signal_date}-${r.buy_date}`}
      dataSource={rows}
      columns={columns}
      loading={loading}
      size="small"
      scroll={{ x: 2100 }}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: true,
        pageSizeOptions: ["20", "50", "100", "200"],
        onChange: onPageChange,
      }}
    />
  );
}
