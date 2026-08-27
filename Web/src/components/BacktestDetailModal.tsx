import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Modal,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "@/components/ui";
import { DownloadOutlined } from "@/components/ui/icons";

import {
  getBacktest,
  getBacktestMetrics,
  listBacktestLedger,
  listBacktestTrades,
  type BacktestSummary,
  type BacktestTask,
} from "@/api/backtest";
import type { StrategyInfo } from "@/api/scan";
import ParamDisplay from "@/components/ParamDisplay";
import EquityCurve from "@/components/EquityCurve";
import MonthlyHeatmap from "@/components/MonthlyHeatmap";
import TradeLedgerTable from "@/components/TradeLedgerTable";
import TradesTable from "@/components/TradesTable";
import StockKlineModal, { type StockKlineTarget } from "@/components/StockKlineModal";
import { formatBeijingTime } from "@/lib/dayjsSetup";

const { Text } = Typography;

const STATUS_TAG: Record<BacktestTask["status"], { color: string; label: string }> = {
  pending: { color: "default", label: "排队中" },
  running: { color: "processing", label: "运行中" },
  done: { color: "success", label: "已完成" },
  error: { color: "error", label: "失败" },
  cancelled: { color: "warning", label: "已取消" },
};

interface Props {
  open: boolean;
  taskId: string | null;
  strategies: StrategyInfo[];
  onClose: () => void;
}

function SummaryStats({ summary, task }: { summary: BacktestSummary; task: BacktestTask }) {
  return (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Statistic title="成交笔数" value={summary.total_trades} />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Statistic
            title="胜率"
            value={summary.win_rate}
            precision={2}
            suffix="%"
            valueStyle={{ color: summary.win_rate >= 50 ? "#3f8600" : "#cf1322" }}
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Statistic
            title="平均收益"
            value={summary.avg_return}
            precision={2}
            suffix="%"
            valueStyle={{ color: summary.avg_return >= 0 ? "#3f8600" : "#cf1322" }}
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Statistic title="中位收益" value={summary.median_return} precision={2} suffix="%" />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Statistic
            title="大赚率(≥+20%)"
            value={summary.big_win_rate}
            precision={2}
            suffix="%"
            valueStyle={{ color: "#3f8600" }}
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Statistic
            title="大亏率(≤-7%)"
            value={summary.big_loss_rate}
            precision={2}
            suffix="%"
            valueStyle={{ color: "#cf1322" }}
          />
        </Col>
      </Row>
      <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
        <Col xs={12} sm={8} md={6}>
          <Statistic
            title="年化收益 (CAGR)"
            value={summary.cagr_pct ?? 0}
            precision={2}
            suffix="%"
            valueStyle={{ color: (summary.cagr_pct ?? 0) >= 0 ? "#3f8600" : "#cf1322" }}
          />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Statistic
            title="夏普比率"
            value={summary.sharpe ?? 0}
            precision={2}
            valueStyle={{
              color:
                (summary.sharpe ?? 0) >= 1
                  ? "#3f8600"
                  : (summary.sharpe ?? 0) >= 0
                  ? "#fa8c16"
                  : "#cf1322",
            }}
          />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Statistic
            title="最大回撤"
            value={summary.max_drawdown_pct ?? 0}
            precision={2}
            suffix="%"
            valueStyle={{ color: "#cf1322" }}
          />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Statistic
            title="Calmar"
            value={summary.calmar ?? 0}
            precision={2}
            valueStyle={{ color: (summary.calmar ?? 0) >= 1 ? "#3f8600" : "#fa8c16" }}
          />
        </Col>
      </Row>
      {(summary.initial_capital ?? 0) > 0 && (
        <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
          <Col xs={12} sm={8} md={6}>
            <Statistic
              title="初始资金"
              value={summary.initial_capital ?? 0}
              precision={0}
              suffix="元"
              formatter={(v) => Number(v).toLocaleString()}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic
              title="累计盈利"
              value={summary.total_profit ?? 0}
              precision={2}
              suffix="元"
              valueStyle={{ color: (summary.total_profit ?? 0) >= 0 ? "#cf1322" : "#3f8600" }}
              formatter={(v) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic
              title="期末现金"
              value={summary.final_capital ?? 0}
              precision={2}
              suffix="元"
              formatter={(v) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="信号数" value={summary.signal_count ?? summary.total_trades} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic
              title="未成交(资金/持仓)"
              value={summary.skipped_count ?? 0}
              valueStyle={{ color: (summary.skipped_count ?? 0) > 0 ? "#fa8c16" : undefined }}
            />
          </Col>
        </Row>
      )}
      {(summary.max_concurrent ?? 0) > 0 && (
        <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>
          最大同时持仓 {summary.max_concurrent} 只 · 组合级资金约束（同日先卖后买，评分高者优先）
          {task.t_plus_1 !== false ? " · T+1 已启用" : " · T+1 已关闭"}
        </Text>
      )}
    </>
  );
}

export default function BacktestDetailModal({ open, taskId, strategies, onClose }: Props) {
  const [recordTab, setRecordTab] = useState<"ledger" | "trades">("ledger");
  const [tradesPage, setTradesPage] = useState(1);
  const [tradesPageSize, setTradesPageSize] = useState(50);
  const [ledgerPage, setLedgerPage] = useState(1);
  const [ledgerPageSize, setLedgerPageSize] = useState(100);
  const [klineOpen, setKlineOpen] = useState(false);
  const [klineStock, setKlineStock] = useState<StockKlineTarget | null>(null);

  useEffect(() => {
    if (open) {
      setRecordTab("ledger");
      setTradesPage(1);
      setLedgerPage(1);
      setKlineOpen(false);
      setKlineStock(null);
    }
  }, [open, taskId]);

  const taskQ = useQuery({
    queryKey: ["bt-task", taskId],
    queryFn: () => getBacktest(taskId!),
    enabled: open && !!taskId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "running" || s === "pending" ? 2_000 : false;
    },
  });

  const task = taskQ.data;
  const taskStatus = task?.status;
  const isFinished = taskStatus === "done" || taskStatus === "error" || taskStatus === "cancelled";

  const tradesQ = useQuery({
    queryKey: ["bt-trades", taskId, taskStatus, tradesPage, tradesPageSize],
    queryFn: () =>
      listBacktestTrades(taskId!, {
        page: tradesPage,
        pageSize: tradesPageSize,
        sortBy: "buy_date",
        desc: false,
      }),
    enabled: open && !!taskId && isFinished,
  });

  const ledgerQ = useQuery({
    queryKey: ["bt-ledger", taskId, taskStatus, ledgerPage, ledgerPageSize],
    queryFn: () => listBacktestLedger(taskId!, { page: ledgerPage, pageSize: ledgerPageSize }),
    enabled: open && !!taskId && isFinished,
  });

  const allTradesQ = useQuery({
    queryKey: ["bt-trades-all", taskId, taskStatus],
    queryFn: () =>
      listBacktestTrades(taskId!, {
        page: 1,
        pageSize: 5000,
        sortBy: "buy_date",
        desc: false,
      }),
    enabled: open && !!taskId && isFinished,
  });

  const tradeByKey = useMemo(() => {
    type TradeRef = { buy_date: string; sell_date: string; signal_date: string };
    const bySignal = new Map<string, TradeRef>();
    const byBuy = new Map<string, TradeRef>();
    const bySell = new Map<string, TradeRef>();
    const norm = (d?: string) => (d ? d.trim().slice(0, 10) : "");

    for (const row of allTradesQ.data?.rows ?? []) {
      const ref: TradeRef = {
        buy_date: row.buy_date,
        sell_date: row.sell_date,
        signal_date: row.signal_date,
      };
      bySignal.set(`${row.code}-${norm(row.signal_date)}`, ref);
      byBuy.set(`${row.code}-${norm(row.buy_date)}`, ref);
      bySell.set(`${row.code}-${norm(row.sell_date)}`, ref);
    }
    return { bySignal, byBuy, bySell };
  }, [allTradesQ.data?.rows]);

  const openStockKline = (stock: StockKlineTarget) => {
    const norm = (d?: string) => (d ? d.trim().slice(0, 10) : "");
    const code = stock.code;
    const trade =
      tradeByKey.bySignal.get(`${code}-${norm(stock.signalDate)}`) ??
      tradeByKey.byBuy.get(`${code}-${norm(stock.buyDate)}`) ??
      tradeByKey.bySell.get(`${code}-${norm(stock.sellDate)}`);

    setKlineStock({
      ...stock,
      signalDate: norm(trade?.signal_date ?? stock.signalDate) || undefined,
      buyDate: norm(trade?.buy_date ?? stock.buyDate) || undefined,
      sellDate: norm(trade?.sell_date ?? stock.sellDate) || undefined,
    });
    setKlineOpen(true);
  };

  const metricsQ = useQuery({
    queryKey: ["bt-metrics", taskId, taskStatus],
    queryFn: () => getBacktestMetrics(taskId!),
    enabled: open && !!taskId && taskStatus === "done",
  });

  const taskStrategy = useMemo(
    () => (task ? strategies.find((s) => s.name === task.strategy_name) : undefined),
    [strategies, task]
  );

  const progress =
    task && task.total > 0
      ? {
          done: task.progress,
          total: task.total,
          trade_count: task.trade_count,
          elapsed: task.elapsed_seconds ?? 0,
        }
      : null;

  const summary = task?.summary ?? null;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width="min(1200px, 96vw)"
      styles={{ body: { maxHeight: "calc(100vh - 120px)", overflowY: "auto", paddingTop: 8 } }}
      title={
        task ? (
          <Space wrap size={8}>
            <Text strong>{task.name || "回测详情"}</Text>
            <Tag color={STATUS_TAG[task.status].color}>{STATUS_TAG[task.status].label}</Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {task.id}
            </Text>
          </Space>
        ) : (
          "回测详情"
        )
      }
    >
      {taskQ.isLoading && (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin spinning tip="加载中…">
            <div style={{ minHeight: 60 }} />
          </Spin>
        </div>
      )}

      {task && (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          {(taskStatus === "running" || taskStatus === "pending") && progress && (
            <Progress
              percent={Math.round((progress.done / progress.total) * 100)}
              status={taskStatus === "running" ? "active" : "normal"}
              format={() =>
                `${progress.done}/${progress.total} · ${progress.trade_count} 笔 · ${progress.elapsed.toFixed(1)}s`
              }
            />
          )}

          {task.error && (
            <Alert type="error" showIcon message="回测异常" description={task.error} />
          )}

          <Card size="small" title="回测配置">
            <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small" bordered>
              <Descriptions.Item label="策略">
                <Tag color="blue">{taskStrategy?.label ?? task.strategy_name}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="回测区间">
                {task.start_date} → {task.end_date}
              </Descriptions.Item>
              <Descriptions.Item label="耗时">
                {task.elapsed_seconds != null ? `${task.elapsed_seconds.toFixed(1)} 秒` : "—"}
              </Descriptions.Item>
              <Descriptions.Item label="止盈">
                +{(task.take_profit * 100).toFixed(0)}%
              </Descriptions.Item>
              <Descriptions.Item label="止损">
                -{(task.stop_loss * 100).toFixed(0)}%
              </Descriptions.Item>
              <Descriptions.Item label="最长持有">{task.max_hold} 日</Descriptions.Item>
              <Descriptions.Item label="分批止盈">
                {task.split_tp != null ? `${(task.split_tp * 100).toFixed(0)}%` : "不分批"}
              </Descriptions.Item>
              <Descriptions.Item label="初始资金">
                {task.initial_capital.toLocaleString()} 元
              </Descriptions.Item>
              <Descriptions.Item label="单笔仓位">
                {(task.position_pct * 100).toFixed(0)}%
              </Descriptions.Item>
              <Descriptions.Item label="最大持仓">{task.max_concurrent} 只</Descriptions.Item>
              <Descriptions.Item label="T+1">{task.t_plus_1 ? "开" : "关"}</Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {formatBeijingTime(task.created_at, "YYYY-MM-DD HH:mm:ss")}
              </Descriptions.Item>
              <Descriptions.Item label="开始时间">
                {formatBeijingTime(task.started_at, "YYYY-MM-DD HH:mm:ss")}
              </Descriptions.Item>
              <Descriptions.Item label="结束时间">
                {formatBeijingTime(task.finished_at, "YYYY-MM-DD HH:mm:ss")}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Collapse
            size="small"
            items={[
              {
                key: "params",
                label: `策略参数（${
                  Object.keys(task.strategy_params ?? {}).length
                    ? `${Object.keys(task.strategy_params ?? {}).length} 项`
                    : "默认"
                }）`,
                children: (
                  <ParamDisplay
                    schema={taskStrategy?.params_schema}
                    params={task.strategy_params ?? {}}
                  />
                ),
              },
            ]}
          />

          {summary && (
            <Card size="small" title="绩效概览">
              <SummaryStats summary={summary} task={task} />
            </Card>
          )}

          {(metricsQ.data?.equity_curve.length || tradesQ.data?.rows.length) ? (
            <Card size="small" title="组合净值曲线">
              <EquityCurve equity={metricsQ.data?.equity_curve} trades={tradesQ.data?.rows} />
            </Card>
          ) : null}

          {metricsQ.data && metricsQ.data.monthly.length > 0 && (
            <Card size="small" title="月度收益热力图">
              <MonthlyHeatmap monthly={metricsQ.data.monthly} />
            </Card>
          )}

          {(tradesQ.data || ledgerQ.data) && (
            <Card
              size="small"
              title={
                <Space wrap>
                  <span>交易记录</span>
                  <Tag
                    color={recordTab === "ledger" ? "blue" : "default"}
                    style={{ cursor: "pointer" }}
                    onClick={() => setRecordTab("ledger")}
                  >
                    买卖流水 ({ledgerQ.data?.total ?? 0})
                  </Tag>
                  <Tag
                    color={recordTab === "trades" ? "blue" : "default"}
                    style={{ cursor: "pointer" }}
                    onClick={() => setRecordTab("trades")}
                  >
                    按笔汇总 ({tradesQ.data?.total ?? 0})
                  </Tag>
                </Space>
              }
              extra={
                <Button
                  icon={<DownloadOutlined />}
                  size="small"
                  href={`/api/backtest/${taskId}/trades.csv`}
                  target="_blank"
                >
                  导出 CSV
                </Button>
              }
            >
              {recordTab === "ledger" && ledgerQ.data && (
                <TradeLedgerTable
                  rows={ledgerQ.data.rows}
                  total={ledgerQ.data.total}
                  page={ledgerPage}
                  pageSize={ledgerPageSize}
                  loading={ledgerQ.isFetching}
                  onStockClick={openStockKline}
                  onPageChange={(p, ps) => {
                    setLedgerPage(p);
                    setLedgerPageSize(ps);
                  }}
                />
              )}
              {recordTab === "trades" && tradesQ.data && (
                <TradesTable
                  rows={tradesQ.data.rows}
                  total={tradesQ.data.total}
                  page={tradesPage}
                  pageSize={tradesPageSize}
                  loading={tradesQ.isFetching}
                  onStockClick={openStockKline}
                  onPageChange={(p, ps) => {
                    setTradesPage(p);
                    setTradesPageSize(ps);
                  }}
                />
              )}
            </Card>
          )}

          {taskStatus === "done" && !summary && !tradesQ.data && (
            <Divider plain>
              <Text type="secondary">暂无成交数据</Text>
            </Divider>
          )}
        </Space>
      )}

      <StockKlineModal
        open={klineOpen}
        stock={klineStock}
        onClose={() => {
          setKlineOpen(false);
          setKlineStock(null);
        }}
      />
    </Modal>
  );
}
