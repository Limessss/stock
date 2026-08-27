import { Skeleton, Typography } from "@/components/ui";

import type { MarketIndexItem, MarketOverview } from "@/api/market";

const { Text } = Typography;

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtAmount(yuan: number | null | undefined): string {
  if (yuan == null || Number.isNaN(yuan)) return "—";
  const yi = yuan / 1e8;
  if (yi >= 10000) return `${(yi / 10000).toFixed(2)}万亿`;
  return `${yi.toFixed(0)}亿`;
}

function pctClass(v: number | null | undefined): string {
  if (v == null || v === 0) return "market-stat-flat";
  return v > 0 ? "market-stat-up" : "market-stat-down";
}

function IndexCell({ item }: { item: MarketIndexItem }) {
  const pctCls = pctClass(item.change_pct);
  return (
    <div className="market-day-overview-item market-day-overview-item--index">
      <span className="market-day-overview-label">{item.name}</span>
      <span className={`market-day-overview-value ${pctCls}`}>
        {item.close != null ? item.close.toFixed(2) : "—"}
        <small className={pctCls}>{fmtPct(item.change_pct)}</small>
      </span>
    </div>
  );
}

interface Props {
  data?: MarketOverview;
  loading?: boolean;
}

export default function MarketDayOverview({ data, loading }: Props) {
  if (loading && !data) {
    return (
      <div className="market-day-overview market-day-overview--loading">
        <Skeleton.Input active size="small" style={{ width: "100%", height: 52 }} />
      </div>
    );
  }

  if (!data) return null;

  if (!data.ready) {
    return (
      <div className="market-day-overview market-day-overview--loading">
        <Text type="secondary" style={{ fontSize: 12 }}>
          行情数据准备中…
        </Text>
      </div>
    );
  }

  const indices =
    data.indices.length > 0
      ? data.indices
      : [
          {
            code: "SH000001",
            name: data.index_name,
            close: data.index_close,
            change_pct: data.index_change_pct,
            change_amt: data.index_change_amt,
          },
        ];

  return (
    <div className="market-day-overview">
      {data.is_non_trading_day && (
        <div className="market-day-overview-hint">
          非交易日，展示 {data.trade_date} 行情
        </div>
      )}
      <div className="market-day-overview-grid market-day-overview-grid--indices">
        {indices.map((item) => (
          <IndexCell key={item.code} item={item} />
        ))}
        <div className="market-day-overview-item market-day-overview-item--stat">
          <span className="market-day-overview-label">上涨</span>
          <span className="market-day-overview-value market-stat-up">
            {data.up_count ?? "—"}
          </span>
        </div>
        <div className="market-day-overview-item market-day-overview-item--stat">
          <span className="market-day-overview-label">下跌</span>
          <span className="market-day-overview-value market-stat-down">
            {data.down_count ?? "—"}
          </span>
        </div>
        <div className="market-day-overview-item market-day-overview-item--stat market-day-overview-item--amount">
          <span className="market-day-overview-label">成交额</span>
          <span className="market-day-overview-value">{fmtAmount(data.total_amount)}</span>
        </div>
      </div>
    </div>
  );
}
