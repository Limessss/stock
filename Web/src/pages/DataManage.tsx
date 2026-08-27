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
} from "@/components/ui";
import {
  CloudDownloadOutlined,
  DatabaseOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
} from "@/components/ui/icons";

import { fetchHealth } from "@/api/health";
import {
  getBuildStatus,
  getCacheStats,
  getTdxSyncStatus,
  startBuild,
  startTdxSync,
} from "@/api/data";
import { formatBeijingTime } from "@/lib/dayjsSetup";
import { getKline } from "@/api/kline";

const { Title, Paragraph, Text } = Typography;

const TDX_STAGE_LABEL: Record<string, string> = {
  idle: "等待更新",
  checking: "检查官方版本",
  downloading: "下载官方日线包",
  extracting: "解压日线文件",
  "downloading-gbbq": "下载 GBBQ 除权资料",
  "parsing-gbbq": "解析 GBBQ 并生成复权事件缓存",
  "using-local-data": "远端未变化，使用本地数据",
  "building-cache": "构建前复权 Parquet",
  done: "更新完成",
  error: "更新失败",
};

function formatProgressValue(value: number, unit: string): string {
  if (unit !== "bytes") return value.toLocaleString();
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export default function DataManagePage() {
  const qc = useQueryClient();
  const { modal, message } = App.useApp();
  const [buildPolling, setBuildPolling] = useState(false);
  const [tdxPolling, setTdxPolling] = useState(false);
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
  const tdxStatusQ = useQuery({
    queryKey: ["tdx-sync-status"],
    queryFn: getTdxSyncStatus,
    refetchInterval: tdxPolling ? 1_000 : false,
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

  if (tdxStatusQ.data && !tdxStatusQ.data.running && tdxPolling) {
    setTdxPolling(false);
    qc.invalidateQueries({ queryKey: ["cache-stats"] });
    qc.invalidateQueries({ queryKey: ["health"] });
    if (tdxStatusQ.data.error) message.error("通达信更新失败：" + tdxStatusQ.data.error);
    else message.success(
      `行情更新完成：解压 ${tdxStatusQ.data.extracted} 个文件，GBBQ ${tdxStatusQ.data.gbbq_events.toLocaleString()} 条，Parquet 更新 ${tdxStatusQ.data.updated} 只`
    );
  }

  const tdxMutation = useMutation({
    mutationFn: (forceDownload: boolean) => startTdxSync(forceDownload),
    onSuccess: (result) => {
      setTdxPolling(true);
      qc.setQueryData(["tdx-sync-status"], result);
      message.info("已开始后台下载与增量构建");
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

  const onTdxSync = () =>
    modal.confirm({
      title: "同步通达信日线、GBBQ 并更新缓存？",
      content: "将分别检查官方日线包与 GBBQ 除权资料的版本。只有远端发生变化时才下载，并在本地计算、缓存前复权行情。",
      okText: "开始更新",
      cancelText: "取消",
      onOk: () => tdxMutation.mutate(false),
    });

  const stats = statsQ.data;
  const bs = buildStatusQ.data;
  const tdx = tdxStatusQ.data;
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
            <Statistic
              title="缓存最近更新"
              value={formatBeijingTime(stats?.last_updated, "YYYY-MM-DD HH:mm:ss")}
            />
          </Card>
        </Col>
      </Row>

      <Card
        style={{ marginTop: 16 }}
        title={<Space><CloudDownloadOutlined /><span>通达信官方数据更新</span></Space>}
        extra={
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            disabled={tdx?.running || bs?.running || tdxMutation.isPending}
            loading={tdxMutation.isPending}
            onClick={onTdxSync}
          >
            {tdx?.running ? "更新中…" : "下载最新数据并构建"}
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          message="通达信日线 + GBBQ · 本地计算前复权 · 版本未变化不重复下载"
          description="状态轮询只读取本机；每次显式同步仅检查一次官方版本，日线或除权资料发生变化时才下载，原始行情会完整保留。"
          style={{ marginBottom: 16 }}
        />
        <Descriptions column={{ xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 2 }} bordered size="small">
          <Descriptions.Item label="当前阶段">{TDX_STAGE_LABEL[tdx?.stage ?? "idle"] ?? tdx?.stage}</Descriptions.Item>
          <Descriptions.Item label="本地最新交易日">{tdx?.last_raw_date || "—"}</Descriptions.Item>
          <Descriptions.Item label="官方更新时间">{tdx?.remote_time || "首次更新时检查"}</Descriptions.Item>
          <Descriptions.Item label="官方包大小">{tdx?.remote_size || "约 500MB"}</Descriptions.Item>
          <Descriptions.Item label="下载文件">{tdx?.download_path || "—"}</Descriptions.Item>
          <Descriptions.Item label="官方来源">
            {tdx?.source_url ? <a href={tdx.source_url} target="_blank" rel="noreferrer">data.tdx.com.cn</a> : "通达信官方"}
          </Descriptions.Item>
          <Descriptions.Item label="GBBQ 事件缓存">{(tdx?.gbbq_events ?? 0).toLocaleString()} 条</Descriptions.Item>
          <Descriptions.Item label="GBBQ 最近解析">{formatBeijingTime(tdx?.gbbq_updated_at, "YYYY-MM-DD HH:mm:ss") || "—"}</Descriptions.Item>
        </Descriptions>
        {tdx?.running && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={tdx.progress_pct} status="active" />
            <Paragraph type="secondary" style={{ marginTop: 4, fontSize: 12 }}>
              {TDX_STAGE_LABEL[tdx.stage] ?? tdx.stage} · {formatProgressValue(tdx.done, tdx.unit)}
              {tdx.total ? ` / ${formatProgressValue(tdx.total, tdx.unit)}` : ""}
              {` · 用时 ${tdx.elapsed_seconds}s`}
            </Paragraph>
          </div>
        )}
        {tdx?.error && <Alert style={{ marginTop: 16 }} type="error" showIcon message="更新失败" description={tdx.error} />}
      </Card>

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
