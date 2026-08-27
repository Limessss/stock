import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import dayjs, { type Dayjs } from "dayjs";
import { useSearchParams } from "react-router-dom";

import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  InputNumber,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "@/components/ui";
import type { ColumnsType } from "@/components/ui";
import { ReloadOutlined } from "@/components/ui/icons";
import {
  fetchIntervalGains,
  type IntervalGainItem,
} from "@/api/sentiment";
import ChineseDatePicker from "@/components/ChineseDatePicker";
import StockKlineModal, { type StockKlineTarget } from "@/components/StockKlineModal";
import { parseApiTime } from "@/lib/dayjsSetup";

const { Title, Text } = Typography;
const QUICK_DAYS = [3, 5, 10, 20, 60];

export default function IntervalGainsPage() {
  const [searchParams] = useSearchParams();
  const [days, setDays] = useState(5);
  const [limit, setLimit] = useState(50);
  const [startDate, setStartDate] = useState<string | undefined>(() => searchParams.get("start") ?? undefined);
  const [endDate, setEndDate] = useState<string | undefined>(() => searchParams.get("end") ?? undefined);
  const [klineTarget, setKlineTarget] = useState<StockKlineTarget | null>(null);

  const query = useQuery({
    queryKey: ["sentiment-interval-gains", startDate ?? "days", endDate ?? "latest", days, limit],
    queryFn: () => fetchIntervalGains({ start: startDate, end: endDate, days, limit }),
    staleTime: 5 * 60_000,
  });

  const columns: ColumnsType<IntervalGainItem> = [
    {
      title: "排名",
      dataIndex: "rank",
      width: 72,
      align: "center",
      render: (rank: number) => (
        <span className={`interval-rank${rank <= 3 ? ` is-top-${rank}` : ""}`}>{rank}</span>
      ),
    },
    {
      title: "股票",
      width: 170,
      render: (_: unknown, item: IntervalGainItem) => (
        <Button
          type="link"
          size="small"
          onClick={() => setKlineTarget({ code: item.code, name: item.name, signalDate: query.data?.end_date })}
        >
          {item.name || item.code}
        </Button>
      ),
    },
    { title: "代码", dataIndex: "code", width: 115, render: (value: string) => <Text code>{value}</Text> },
    {
      title: `起始收盘${query.data ? `（${dayjs(query.data.start_date).format("MM-DD")}）` : ""}`,
      dataIndex: "start_close",
      width: 145,
      align: "right",
      render: (value: number) => value.toFixed(2),
    },
    {
      title: `结束收盘${query.data ? `（${dayjs(query.data.end_date).format("MM-DD")}）` : ""}`,
      dataIndex: "end_close",
      width: 145,
      align: "right",
      render: (value: number) => value.toFixed(2),
    },
    {
      title: `${query.data?.days ?? days}日涨幅`,
      dataIndex: "gain_pct",
      width: 130,
      align: "right",
      render: (value: number) => (
        <strong className={value >= 0 ? "interval-gain-positive" : "interval-gain-negative"}>
          {value > 0 ? "+" : ""}{value.toFixed(2)}%
        </strong>
      ),
    },
  ];

  return (
    <div className="sentiment-page interval-gains-page">
      <div className="sentiment-page-header">
        <div>
          <Title level={3} style={{ margin: 0 }}>区间涨幅</Title>
          <Text type="secondary">基于本地通达信收盘价 · 不请求外部接口 · 相同区间自动缓存</Text>
        </div>
      </div>

      <Card className="interval-gains-toolbar">
        <Space wrap size={[12, 10]}>
          <Text type="secondary">区间交易日</Text>
          <Segmented
            value={!startDate && QUICK_DAYS.includes(days) ? days : undefined}
            options={QUICK_DAYS.map((value) => ({ label: `${value}日`, value }))}
            onChange={(value) => {
              setDays(Number(value));
              setStartDate(undefined);
            }}
          />
          <InputNumber
            min={1}
            max={250}
            value={days}
            onChange={(value: number | null) => {
              if (value != null) {
                setDays(Math.max(1, Math.min(250, value)));
                setStartDate(undefined);
              }
            }}
            style={{ width: 90 }}
          />
          <Text type="secondary">起始日期</Text>
          <ChineseDatePicker
            allowClear
            value={startDate ? dayjs(startDate) : null}
            placeholder="按交易日数计算"
            onChange={(value: Dayjs | null) => setStartDate(value?.format("YYYY-MM-DD"))}
          />
          <Text type="secondary">结束日期</Text>
          <ChineseDatePicker
            allowClear
            value={endDate ? dayjs(endDate) : null}
            placeholder="最新交易日"
            onChange={(value: Dayjs | null) => setEndDate(value?.format("YYYY-MM-DD"))}
          />
          <Text type="secondary">展示</Text>
          <Select
            value={limit}
            style={{ width: 105 }}
            options={[50, 100, 200, 500].map((value) => ({ label: `前 ${value} 名`, value }))}
            onChange={(value) => setLimit(Number(value))}
          />
          <Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => query.refetch()}>刷新</Button>
        </Space>
      </Card>

      {query.isLoading && <Card className="interval-gains-loading"><Spin size="large" /><Text type="secondary">正在读取本地收盘价矩阵并计算排行…</Text></Card>}
      {query.error && <Alert type="error" showIcon message="区间涨幅统计失败" description={(query.error as Error).message} />}

      {query.data && (
        <>
          <Row gutter={[12, 12]} className="interval-gains-summary">
            <Col xs={12} md={6}><Card><Statistic title="统计区间" value={`${query.data.start_date} → ${query.data.end_date}`} /></Card></Col>
            <Col xs={12} md={6}><Card><Statistic title="交易日跨度" value={query.data.days} suffix="日" /></Card></Col>
            <Col xs={12} md={6}><Card><Statistic title="有效股票" value={query.data.scanned_stocks} suffix="只" /></Card></Col>
            <Col xs={12} md={6}><Card><Statistic title="数据状态" value={query.data.cache_hit ? "读取缓存" : "本次生成"} suffix={<Tag color={query.data.cache_hit ? "blue" : "green"}>本地</Tag>} /></Card></Col>
          </Row>

          <Card
            title={`涨幅排行 Top ${query.data.items.length}`}
            extra={<Text type="secondary">生成于 {parseApiTime(query.data.generated_at).format("YYYY-MM-DD HH:mm:ss")}</Text>}
          >
            {query.data.items.length ? (
              <Table
                rowKey="code"
                columns={columns}
                dataSource={query.data.items}
                pagination={false}
                size="small"
                scroll={{ x: 880 }}
              />
            ) : <Empty description="该区间没有同时具备起止日行情的股票" />}
          </Card>
        </>
      )}

      <StockKlineModal open={!!klineTarget} stock={klineTarget} onClose={() => setKlineTarget(null)} />
    </div>
  );
}
