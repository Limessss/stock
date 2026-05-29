import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Progress,
  Row,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { DatabaseOutlined, ThunderboltOutlined } from "@ant-design/icons";

import { fetchHealth } from "@/api/health";
import { getBuildStatus, getCacheStats, startBuild } from "@/api/data";

const { Title, Paragraph } = Typography;

export default function HealthPage() {
  const qc = useQueryClient();
  const { modal, message } = App.useApp();
  const [buildPolling, setBuildPolling] = useState(false);

  const healthQ = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

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

  // 当后台任务结束时停止轮询
  useEffect(() => {
    if (buildStatusQ.data && !buildStatusQ.data.running && buildPolling) {
      setBuildPolling(false);
      qc.invalidateQueries({ queryKey: ["cache-stats"] });
      qc.invalidateQueries({ queryKey: ["health"] });
      if (buildStatusQ.data.error) {
        message.error("构建失败：" + buildStatusQ.data.error);
      } else {
        message.success(
          `构建完成，用时 ${buildStatusQ.data.elapsed_seconds}s，处理 ${buildStatusQ.data.total} 文件`
        );
      }
    }
  }, [buildStatusQ.data, buildPolling, qc, message]);

  const buildMutation = useMutation({
    mutationFn: () => startBuild(),
    onSuccess: () => {
      setBuildPolling(true);
      message.info("构建任务已启动，正在后台运行");
    },
    onError: (e: Error) => message.error("启动失败：" + e.message),
  });

  const onBuild = () => {
    modal.confirm({
      title: "构建全市场 Parquet 缓存？",
      content:
        "首次构建大约需要 5-8 分钟，会扫描所有 sh/sz .day 文件并落地为 Parquet。期间可以保持页面打开。",
      okText: "开始构建",
      cancelText: "取消",
      onOk: () => buildMutation.mutate(),
    });
  };

  if (healthQ.isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 64 }}>
        <Spin tip="正在检查后端服务..." />
      </div>
    );
  }

  if (healthQ.error || !healthQ.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="无法连接后端服务"
        description={
          <>
            <Paragraph>请确认 FastAPI 服务正在 http://localhost:8000 运行。</Paragraph>
            <Paragraph type="secondary">
              启动命令：
              <code> uv run uvicorn backend.app.main:app --reload --port 8000</code>
            </Paragraph>
          </>
        }
      />
    );
  }

  const stats = statsQ.data;
  const bs = buildStatusQ.data;

  return (
    <>
      <Title level={3} style={{ marginTop: 0 }}>
        系统状态
      </Title>

      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card>
            <Statistic
              title="后端服务"
              value={healthQ.data.status === "ok" ? "正常" : "异常"}
              valueStyle={{ color: healthQ.data.status === "ok" ? "#3f8600" : "#cf1322" }}
            />
            <Tag color="blue" style={{ marginTop: 8 }}>
              v{healthQ.data.version}
            </Tag>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="沪市 .day 文件" value={healthQ.data.data.sh_day_files} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="深市 .day 文件" value={healthQ.data.data.sz_day_files} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Parquet 缓存文件"
              value={healthQ.data.data.cache_files}
              suffix={stats ? `/ ${stats.total_size_mb} MB` : undefined}
            />
            {healthQ.data.data.cache_files === 0 && (
              <Tag color="orange" style={{ marginTop: 8 }}>
                未构建
              </Tag>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="股票名称映射" value={healthQ.data.data.stock_names} suffix="只" />
            {healthQ.data.data.stock_names === 0 ? (
              <Tag color="orange" style={{ marginTop: 8 }}>
                未生成
              </Tag>
            ) : (
              <Paragraph type="secondary" style={{ marginTop: 8, fontSize: 12 }}>
                由 scripts/build_stock_names.py 从沪深交易所官方清单拉取
              </Paragraph>
            )}
          </Card>
        </Col>
      </Row>

      <Card
        style={{ marginTop: 24 }}
        title={
          <>
            <DatabaseOutlined /> Parquet 缓存
          </>
        }
        extra={
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            disabled={bs?.running || buildMutation.isPending}
            loading={buildMutation.isPending}
            onClick={onBuild}
          >
            {bs?.running ? "构建中…" : "构建全市场缓存"}
          </Button>
        }
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="原始数据目录">
            {healthQ.data.data.raw_dir}
          </Descriptions.Item>
          <Descriptions.Item label="缓存目录">
            {healthQ.data.data.cache_dir}
          </Descriptions.Item>
          <Descriptions.Item label="已缓存股票数">{stats?.total_files ?? 0}</Descriptions.Item>
          <Descriptions.Item label="总 K 线条数">
            {(stats?.total_rows ?? 0).toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="磁盘占用">
            {stats?.total_size_mb ?? 0} MB
          </Descriptions.Item>
          <Descriptions.Item label="最近更新">
            {stats?.last_updated || "—"}
          </Descriptions.Item>
        </Descriptions>

        {bs?.running && (
          <div style={{ marginTop: 16 }}>
            <Progress
              percent={bs.progress_pct}
              status="active"
              format={() => `${bs.done}/${bs.total}`}
            />
            <Paragraph type="secondary" style={{ marginTop: 4 }}>
              用时 {bs.elapsed_seconds}s，预计剩余 ~
              {bs.done > 0 && bs.total > 0
                ? Math.round((bs.elapsed_seconds / bs.done) * (bs.total - bs.done))
                : "?"}
              s
            </Paragraph>
          </div>
        )}
      </Card>
    </>
  );
}
