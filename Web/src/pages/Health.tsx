import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Database, Files, Server } from "lucide-react";

import { Alert, App, Button, Card, Descriptions, Progress, Spin, Tag, Typography } from "@/components/ui";
import { ThunderboltOutlined } from "@/components/ui/icons";
import { fetchHealth } from "@/api/health";
import { getBuildStatus, getCacheStats, startBuild } from "@/api/data";
import { formatBeijingTime } from "@/lib/dayjsSetup";

const { Title, Paragraph, Text } = Typography;

function MetricCard({ icon, label, value, detail, tone = "default" }: { icon: ReactNode; label: string; value: ReactNode; detail?: ReactNode; tone?: "default" | "success" | "warning" }) {
  return (
    <Card className={`overview-metric is-${tone}`}>
      <div className="overview-metric-top"><span className="overview-metric-icon">{icon}</span><span className="overview-metric-label">{label}</span></div>
      <div className="overview-metric-value">{value}</div>
      {detail && <div className="overview-metric-detail">{detail}</div>}
    </Card>
  );
}

export default function HealthPage() {
  const qc = useQueryClient();
  const { modal, message } = App.useApp();
  const [buildPolling, setBuildPolling] = useState(false);

  const healthQ = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 30_000 });
  const statsQ = useQuery({ queryKey: ["cache-stats"], queryFn: getCacheStats, refetchInterval: buildPolling ? 2_000 : 30_000 });
  const buildStatusQ = useQuery({ queryKey: ["build-status"], queryFn: getBuildStatus, enabled: buildPolling, refetchInterval: buildPolling ? 1_000 : false });

  useEffect(() => {
    if (buildStatusQ.data && !buildStatusQ.data.running && buildPolling) {
      setBuildPolling(false);
      qc.invalidateQueries({ queryKey: ["cache-stats"] });
      qc.invalidateQueries({ queryKey: ["health"] });
      if (buildStatusQ.data.error) message.error("构建失败：" + buildStatusQ.data.error);
      else message.success(`构建完成，用时 ${buildStatusQ.data.elapsed_seconds}s，处理 ${buildStatusQ.data.total} 文件`);
    }
  }, [buildStatusQ.data, buildPolling, qc, message]);

  const buildMutation = useMutation({
    mutationFn: () => startBuild(),
    onSuccess: () => { setBuildPolling(true); message.info("构建任务已启动，正在后台运行"); },
    onError: (error: Error) => message.error("启动失败：" + error.message),
  });

  const onBuild = () => modal.confirm({
    title: "构建全市场 Parquet 缓存？",
    content: "首次构建大约需要 5-8 分钟，会扫描沪深 .day 文件并落地为 Parquet。",
    okText: "开始构建",
    cancelText: "取消",
    onOk: () => buildMutation.mutate(),
  });

  if (healthQ.isLoading) return <div className="page-loading"><Spin tip="正在检查后端服务…" /></div>;
  if (healthQ.error || !healthQ.data) {
    return <Alert type="error" showIcon message="无法连接后端服务" description={<><Paragraph>请确认 FastAPI 服务正在 http://localhost:8000 运行。</Paragraph><Paragraph type="secondary"><code>uv run uvicorn backend.app.main:app --reload --port 8000</code></Paragraph></>} />;
  }

  const health = healthQ.data;
  const stats = statsQ.data;
  const build = buildStatusQ.data;
  const marketFiles = health.data.sh_day_files + health.data.sz_day_files;

  return (
    <div className="overview-page">
      <div className="page-heading">
        <div>
          <Title level={2}>数据概览</Title>
          <Paragraph type="secondary">本地行情、证券清单与计算缓存的运行状态</Paragraph>
        </div>
        <div className="page-heading-meta"><span className="status-indicator is-online" />服务在线 <Tag color="blue">v{health.version}</Tag></div>
      </div>

      <div className="overview-metric-grid">
        <MetricCard icon={<Server size={18} />} label="后端服务" value={health.status === "ok" ? "运行正常" : "服务异常"} detail="FastAPI · localhost:8000" tone={health.status === "ok" ? "success" : "warning"} />
        <MetricCard icon={<Files size={18} />} label="本地行情文件" value={marketFiles.toLocaleString()} detail={<span>沪市 {health.data.sh_day_files.toLocaleString()} · 深市 {health.data.sz_day_files.toLocaleString()}</span>} />
        <MetricCard icon={<Database size={18} />} label="Parquet 缓存" value={health.data.cache_files.toLocaleString()} detail={stats ? `${stats.total_size_mb.toLocaleString()} MB 已落盘` : "正在读取缓存统计"} tone={health.data.cache_files > 0 ? "success" : "warning"} />
        <MetricCard icon={<BookOpen size={18} />} label="证券名称映射" value={`${health.data.stock_names.toLocaleString()} 只`} detail="沪深交易所官方清单" tone={health.data.stock_names > 0 ? "success" : "warning"} />
      </div>

      <Card
        className="overview-cache-card"
        title={<div className="section-title"><Database size={17} /><div><strong>行情缓存</strong><small>用于扫描、回测和情绪周期的统一本地数据层</small></div></div>}
        extra={<Button type="primary" icon={<ThunderboltOutlined />} disabled={build?.running || buildMutation.isPending} loading={buildMutation.isPending} onClick={onBuild}>{build?.running ? "构建中…" : "构建全市场缓存"}</Button>}
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="原始数据目录"><Text code>{health.data.raw_dir}</Text></Descriptions.Item>
          <Descriptions.Item label="缓存目录"><Text code>{health.data.cache_dir}</Text></Descriptions.Item>
          <Descriptions.Item label="已缓存证券">{(stats?.total_files ?? 0).toLocaleString()} 只</Descriptions.Item>
          <Descriptions.Item label="K 线总量">{(stats?.total_rows ?? 0).toLocaleString()} 条</Descriptions.Item>
          <Descriptions.Item label="磁盘占用">{stats?.total_size_mb ?? 0} MB</Descriptions.Item>
          <Descriptions.Item label="最近更新">{formatBeijingTime(stats?.last_updated, "YYYY-MM-DD HH:mm:ss")}</Descriptions.Item>
        </Descriptions>

        {build?.running && <div className="overview-build-progress"><div className="overview-build-copy"><strong>正在构建缓存</strong><span>已完成 {build.done}/{build.total} · 用时 {build.elapsed_seconds}s</span></div><Progress percent={build.progress_pct} status="active" format={() => `${build.progress_pct}%`} /></div>}
      </Card>
    </div>
  );
}
