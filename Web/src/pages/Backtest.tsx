import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Input,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from "@/components/ui";
import {
  PlayCircleOutlined,
  HistoryOutlined,
  EyeOutlined,
} from "@/components/ui/icons";
import dayjs, { type Dayjs } from "dayjs";

import {
  createBacktest,
  deleteBacktest,
  getBacktest,
  listBacktestHistory,
  subscribeBacktest,
  type BacktestSummary,
  type BacktestTask,
  type WsMessage,
} from "@/api/backtest";
import { fetchStrategies } from "@/api/strategies";
import BacktestDetailModal from "@/components/BacktestDetailModal";
import BacktestHistoryTable from "@/components/BacktestHistoryTable";
import BacktestRuntimeFields from "@/components/BacktestRuntimeFields";
import ParamForm from "@/components/ParamForm";
import { toBacktestApiPayload, type BacktestRuntimeState } from "@/lib/backtestRuntime";

const { Title, Text } = Typography;

const STATUS_TAG: Record<BacktestTask["status"], { color: string; label: string }> = {
  pending: { color: "default", label: "排队中" },
  running: { color: "processing", label: "运行中" },
  done: { color: "success", label: "已完成" },
  error: { color: "error", label: "失败" },
  cancelled: { color: "warning", label: "已取消" },
};

interface FormState {
  name: string;
  strategyName: string;
  params: Record<string, unknown>;
  startDate: Dayjs;
  endDate: Dayjs;
  takeProfit: number;
  stopLoss: number;
  maxHold: number;
  splitTp: number | null;
  debugMode: boolean;
  maxCodes: number | null;
  numWorkers: number | null;
  engine: "legacy" | "vectorbt";
  initialCapital: number;
  positionPct: number;
  maxConcurrent: number;
  tPlus1: boolean;
}

function formToRuntime(form: FormState): BacktestRuntimeState {
  return {
    startDate: form.startDate,
    endDate: form.endDate,
    takeProfit: form.takeProfit,
    stopLoss: form.stopLoss,
    maxHold: form.maxHold,
    splitTp: form.splitTp,
    debugMode: form.debugMode,
    maxCodes: form.maxCodes,
    numWorkers: form.numWorkers,
    engine: form.engine,
    initialCapital: form.initialCapital,
    positionPct: form.positionPct,
    maxConcurrent: form.maxConcurrent,
    tPlus1: form.tPlus1,
  };
}

function runtimeToForm(form: FormState, rt: BacktestRuntimeState): FormState {
  return { ...form, ...rt };
}

export default function BacktestPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  const [form, setForm] = useState<FormState>({
    name: "",
    strategyName: "breakout_washout",
    params: {},
    startDate: dayjs("2026-01-01"),
    endDate: dayjs("2026-05-28"),
    takeProfit: 0.20,
    stopLoss: 0.07,
    maxHold: 20,
    splitTp: null,
    debugMode: false,
    maxCodes: 200,
    numWorkers: 8,
    engine: "legacy",
    initialCapital: 1_000_000,
    positionPct: 1.0,
    maxConcurrent: 1,
    tPlus1: true,
  });

  const [runTaskId, setRunTaskId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);
  const [wsMsg, setWsMsg] = useState<WsMessage | null>(null);
  const wsCloseRef = useRef<(() => void) | null>(null);

  const defaultStrategyApplied = useRef(false);

  const { data: strategyPack } = useQuery({
    queryKey: ["strategies"],
    queryFn: fetchStrategies,
    staleTime: 30_000,
  });
  const strategies = strategyPack?.strategies;

  useEffect(() => {
    if (!strategyPack || defaultStrategyApplied.current) return;
    defaultStrategyApplied.current = true;
    setForm((f) => ({ ...f, strategyName: strategyPack.default_strategy }));
  }, [strategyPack]);

  const currentStrategy = useMemo(
    () => strategies?.find((s) => s.name === form.strategyName),
    [strategies, form.strategyName]
  );

  // 历史任务
  const historyQ = useQuery({
    queryKey: ["bt-history"],
    queryFn: () => listBacktestHistory(100),
    refetchInterval: runTaskId ? 5_000 : 30_000,
  });

  const runTaskQ = useQuery({
    queryKey: ["bt-task", runTaskId],
    queryFn: () => getBacktest(runTaskId!),
    enabled: !!runTaskId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "running" || s === "pending" ? 2_000 : false;
    },
  });

  const runTaskStatus = runTaskQ.data?.status;

  const openDetail = (id: string) => {
    setDetailTaskId(id);
    setDetailOpen(true);
  };

  // 启动回测 + 订阅 WebSocket
  const startMutation = useMutation({
    mutationFn: () => {
      const rt = formToRuntime(form);
      const payload = toBacktestApiPayload(rt);
      return createBacktest({
        name: form.name || null,
        strategy: form.strategyName,
        params: form.params,
        ...payload,
      });
    },
    onSuccess: (r) => {
      setRunTaskId(r.task_id);
      setWsMsg(null);
      // 关闭老连接
      wsCloseRef.current?.();
      // 新建 WebSocket 订阅
      wsCloseRef.current = subscribeBacktest(
        r.task_id,
        (m) => setWsMsg(m),
        () => (wsCloseRef.current = null)
      );
      message.success("任务已启动 " + r.task_id);
    },
    onError: (e: Error) => message.error("启动失败：" + e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBacktest,
    onSuccess: (_, deletedId) => {
      message.success("已删除");
      if (runTaskId === deletedId) {
        setRunTaskId(null);
        wsCloseRef.current?.();
      }
      if (detailTaskId === deletedId) {
        setDetailOpen(false);
        setDetailTaskId(null);
      }
      queryClient.invalidateQueries({ queryKey: ["bt-history"] });
    },
    onError: (e: Error) => message.error("删除失败：" + e.message),
  });

  useEffect(
    () => () => {
      wsCloseRef.current?.();
    },
    []
  );

  const progress = wsMsg
    ? (wsMsg.type === "progress"
        ? { done: wsMsg.done, total: wsMsg.total, trade_count: wsMsg.trade_count, elapsed: wsMsg.elapsed_seconds }
        : wsMsg.type === "snapshot"
        ? { done: wsMsg.done, total: wsMsg.total, trade_count: wsMsg.trade_count, elapsed: wsMsg.elapsed_seconds ?? 0 }
        : wsMsg.type === "done"
        ? { done: 1, total: 1, trade_count: wsMsg.trade_count, elapsed: wsMsg.elapsed_seconds }
        : null)
    : runTaskQ.data
    ? {
        done: runTaskQ.data.progress,
        total: runTaskQ.data.total,
        trade_count: runTaskQ.data.trade_count,
        elapsed: runTaskQ.data.elapsed_seconds ?? 0,
      }
    : null;

  const runSummary: BacktestSummary | null =
    (wsMsg?.type === "done" ? wsMsg.summary : null) ?? runTaskQ.data?.summary ?? null;

  return (
    <>
      <div className="page-heading">
        <div>
          <Title level={2}>回测中心</Title>
          <Typography.Paragraph type="secondary">配置策略、资金与执行规则，验证历史区间表现</Typography.Paragraph>
        </div>
      </div>

      <Card title="回测配置" className="workbench-form-card" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]}>
          <Col xs={24} md={8} className="workbench-field">
            <label>任务名称</label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="便于历史区分（可空）"
            />
          </Col>
          <Col xs={24} md={6} className="workbench-field">
            <label>回测策略</label>
            <Select
              value={form.strategyName}
              onChange={(v) => setForm({ ...form, strategyName: v, params: {} })}
              options={(strategies ?? []).map((s) => ({ label: s.label, value: s.name }))}
              style={{ width: "100%" }}
            />
          </Col>
        </Row>
        <div style={{ marginTop: 12 }}>
          <BacktestRuntimeFields
            value={formToRuntime(form)}
            onChange={(rt) => setForm(runtimeToForm(form, rt))}
          />
        </div>

        {currentStrategy && <div className="workbench-form-section">
          <div className="workbench-form-section-head"><strong>策略参数</strong><span>{currentStrategy.label}</span></div>
          <ParamForm schema={currentStrategy.params_schema} value={form.params} onChange={(v) => setForm({ ...form, params: v })} />
        </div>}

        <div style={{ marginTop: 16, textAlign: "right" }}>
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            loading={startMutation.isPending}
            onClick={() => startMutation.mutate()}
          >
            启动回测
          </Button>
        </div>
      </Card>

      {/* 当前运行任务进度（新建回测） */}
      {runTaskId && (
        <Card
          style={{ marginBottom: 16 }}
          title={
            <Space>
              <Text strong>运行中 {runTaskId.slice(0, 8)}…</Text>
              {runTaskQ.data && (
                <Tag color={STATUS_TAG[runTaskQ.data.status].color}>
                  {STATUS_TAG[runTaskQ.data.status].label}
                </Tag>
              )}
            </Space>
          }
          extra={
            runTaskStatus === "done" && (
              <Button
                type="link"
                icon={<EyeOutlined />}
                onClick={() => openDetail(runTaskId)}
              >
                查看完整结果
              </Button>
            )
          }
        >
          {progress && progress.total > 0 && (
            <Progress
              percent={Math.round((progress.done / progress.total) * 100)}
              status={
                runTaskStatus === "running"
                  ? "active"
                  : runTaskStatus === "error"
                  ? "exception"
                  : "success"
              }
              format={() =>
                `${progress.done}/${progress.total}  ·  ${progress.trade_count} 笔  ·  ${
                  progress.elapsed?.toFixed(1) ?? "?"
                }s`
              }
            />
          )}

          {runTaskQ.data?.error && (
            <Alert
              type="error"
              showIcon
              message="回测异常"
              description={runTaskQ.data.error}
              style={{ marginTop: 12 }}
            />
          )}

          {runSummary && runTaskStatus === "done" && (
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={6}>
                <Statistic title="成交笔数" value={runSummary.total_trades} />
              </Col>
              <Col span={6}>
                <Statistic
                  title="胜率"
                  value={runSummary.win_rate}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: runSummary.win_rate >= 50 ? "#3f8600" : "#cf1322" }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="平均收益"
                  value={runSummary.avg_return}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: runSummary.avg_return >= 0 ? "#3f8600" : "#cf1322" }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="累计盈利"
                  value={runSummary.total_profit ?? 0}
                  precision={2}
                  suffix="元"
                  formatter={(v) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                />
              </Col>
            </Row>
          )}
        </Card>
      )}

      {/* 历史 */}
      <Card title={<><HistoryOutlined /> 历史回测</>}>
        <BacktestHistoryTable
          tasks={historyQ.data ?? []}
          strategies={strategies ?? []}
          loading={historyQ.isLoading}
          onSelect={openDetail}
          onDelete={(id) => deleteMutation.mutate(id)}
          deletingId={deleteMutation.isPending ? deleteMutation.variables : undefined}
        />
      </Card>

      <BacktestDetailModal
        open={detailOpen}
        taskId={detailTaskId}
        strategies={strategies ?? []}
        onClose={() => {
          setDetailOpen(false);
          setDetailTaskId(null);
        }}
      />
    </>
  );
}
