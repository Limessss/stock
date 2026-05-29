import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  DatabaseOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

import { fetchHealth } from "@/api/health";
import { getBuildStatus, getCacheStats, startBuild } from "@/api/data";
import { getKline } from "@/api/diagnose";

const { Title, Paragraph, Text } = Typography;

export default function DataManagePage() {
  const qc = useQueryClient();
  const { modal, message } = App.useApp();
  const [buildPolling, setBuildPolling] = useState(false);
  const [code, setCode] = useState("sz000001");
  const [queriedCode, setQueriedCode] = useState<string | null>(null);

  const healthQ = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 30_000 });
  const statsQ = useQuery({
    queryKey: ["cache-stats"],
    queryFn: getCacheStats,
    refetchInterval: buildPolling ? 2_000 : 30_000,
  });
  const buildStatusQ = useQuery({
    queryKey: ["build-status"],
    queryFn: getBuildStatus,
    enabled: buildPolling,
    refetchInterval: buildPolling ? 1_000 : false,
  });

  if (buildStatusQ.data && !buildStatusQ.data.running && buildPolling) {
    setBuildPolling(false);
    qc.invalidateQueries({ queryKey: ["cache-stats"] });
    qc.invalidateQueries({ queryKey: ["health"] });
    if (buildStatusQ.data.error) message.error("构建失败：" + buildStatusQ.data.error);
    else message.success(
      `构建完成：更新 ${buildStatusQ.data.updated ?? 0} 只，跳过 ${buildStatusQ.data.skipped ?? 0} 只，用时 ${buildStatusQ.data.elapsed_seconds}s`
    );
  }

  const buildMutation = useMutation({
    mutationFn: (incremental: boolean) => startBuild({ incremental }),
    onSuccess: () => {
      setBuildPolling(true);
      message.info("构建任务已启动");
    },
    onError: (e: Error) => message.error("启动失败：" + e.message),
  });

  const klineQ = useQuery({
    queryKey: ["kline-inspect", queriedCode],
    queryFn: () => getKline(queriedCode!, { lastN: 30 }),
    enabled: !!queriedCode,
    retry: 0,
  });

  const onIncremental = () =>
    modal.confirm({
      title: "增量更新 Parquet 缓存？",
      content: "仅重建「末日有变化」或尚无缓存的股票，通达信每日更新后通常几十秒～数分钟。",
      okText: "开始",
      cancelText: "取消",
      onOk: () => buildMutation.mutate(true),
    });

  const onFullBuild = () =>
    modal.confirm({
      title: "全量重建 Parquet 缓存？",
      content: "扫描全部 .day 并重写 Parquet，约 5–8 分钟。仅在首次或修正历史数据时使用。",
      okText: "开始",
      cancelText: "取消",
      onOk: () => buildMutation.mutate(false),
    });

  const stats = statsQ.data;
  const bs = buildStatusQ.data;
  const kline = klineQ.data;

  return (
    <>
      <Title level={3} style={{ marginTop: 0 }}>
        <DatabaseOutlined /> 数据管理
      </Title>

      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card>
            <Statistic title="原始 .day 文件" value={(healthQ.data?.data.sh_day_files ?? 0) + (healthQ.data?.data.sz_day_files ?? 0)} />
            <Paragraph type="secondary" style={{ marginTop: 8, fontSize: 11 }}>
              沪 {healthQ.data?.data.sh_day_files ?? 0} · 深 {healthQ.data?.data.sz_day_files ?? 0}
            </Paragraph>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Parquet 缓存"
              value={stats?.total_files ?? 0}
              suffix={stats ? `/ ${stats.total_size_mb} MB` : undefined}
            />
            <Paragraph type="secondary" style={{ marginTop: 8, fontSize: 11 }}>
              共 {(stats?.total_rows ?? 0).toLocaleString()} 条 K 线
            </Paragraph>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="股票名称映射" value={healthQ.data?.data.stock_names ?? 0} suffix="只" />
            {(healthQ.data?.data.stock_names ?? 0) === 0 && (
              <Tag color="orange" style={{ marginTop: 8 }}>未生成</Tag>
            )}
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="缓存最近更新" value={stats?.last_updated || "—"} />
          </Card>
        </Col>
      </Row>

      <Card
        style={{ marginTop: 16 }}
        title="缓存构建"
        extra={
          <Space>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              disabled={bs?.running || buildMutation.isPending}
              loading={buildMutation.isPending}
              onClick={onIncremental}
            >
              {bs?.running ? "构建中…" : "增量更新"}
            </Button>
            <Button
              icon={<ReloadOutlined />}
              disabled={bs?.running || buildMutation.isPending}
              onClick={onFullBuild}
            >
              全量重建
            </Button>
          </Space>
        }
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="原始数据目录">{healthQ.data?.data.raw_dir}</Descriptions.Item>
          <Descriptions.Item label="缓存目录">{healthQ.data?.data.cache_dir}</Descriptions.Item>
        </Descriptions>
        {bs?.running && (
          <div style={{ marginTop: 16 }}>
            <Progress
              percent={bs.progress_pct}
              status="active"
              format={() => `${bs.done}/${bs.total}`}
            />
            <Paragraph type="secondary" style={{ marginTop: 4, fontSize: 12 }}>
              用时 {bs.elapsed_seconds}s
              {(bs.updated ?? 0) > 0 || (bs.skipped ?? 0) > 0
                ? ` · 更新 ${bs.updated ?? 0} 只 · 跳过 ${bs.skipped ?? 0} 只`
                : ""}
            </Paragraph>
          </div>
        )}
      </Card>

      <Card
        style={{ marginTop: 16 }}
        title={
          <Space>
            <SearchOutlined />
            <span>单股缓存查询</span>
            <Text type="secondary" style={{ fontSize: 12 }}>
              验证某只股票的缓存是否最新（看最近 30 个交易日数据）
            </Text>
          </Space>
        }
      >
        <Space.Compact style={{ width: "100%", marginBottom: 12 }}>
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value.trim().toLowerCase())}
            placeholder="例如 sz000001 / sh600519"
            onPressEnter={() => setQueriedCode(code)}
            style={{ maxWidth: 280 }}
          />
          <Button type="primary" icon={<ReloadOutlined />} onClick={() => setQueriedCode(code)}>
            查询
          </Button>
        </Space.Compact>

        {klineQ.error && (
          <Alert type="error" showIcon message="加载失败" description={(klineQ.error as Error).message} />
        )}

        {kline && (() => {
          const ma10Map = new Map(kline.ma10.map((p) => [p.time, p.value]));
          const volMap = new Map(kline.volume.map((p) => [p.time, p.value]));
          const rows = kline.candles
            .map((c) => ({ ...c, vol: volMap.get(c.time) ?? 0, ma10: ma10Map.get(c.time) ?? null }))
            .reverse();
          return (
            <>
              <Descriptions column={3} size="small" style={{ marginBottom: 12 }}>
                <Descriptions.Item label="股票">
                  <Text code>{kline.code}</Text> {kline.name}
                </Descriptions.Item>
                <Descriptions.Item label="返回行数">{kline.candles.length}</Descriptions.Item>
                <Descriptions.Item label="日期范围">
                  {kline.candles[0]?.time} → {kline.candles[kline.candles.length - 1]?.time}
                </Descriptions.Item>
              </Descriptions>
              <Table
                size="small"
                rowKey="time"
                pagination={{ pageSize: 10 }}
                dataSource={rows}
                columns={[
                  { title: "日期", dataIndex: "time" },
                  { title: "开", dataIndex: "open", align: "right", render: (v: number) => v.toFixed(2) },
                  { title: "高", dataIndex: "high", align: "right", render: (v: number) => v.toFixed(2) },
                  { title: "低", dataIndex: "low", align: "right", render: (v: number) => v.toFixed(2) },
                  { title: "收", dataIndex: "close", align: "right", render: (v: number) => v.toFixed(2) },
                  { title: "量", dataIndex: "vol", align: "right", render: (v: number) => v.toLocaleString() },
                  {
                    title: "MA10",
                    dataIndex: "ma10",
                    align: "right",
                    render: (v: number | null) => (v == null ? "—" : v.toFixed(2)),
                  },
                ]}
              />
            </>
          );
        })()}
      </Card>
    </>
  );
}
