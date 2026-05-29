import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { Link, useSearchParams } from "react-router-dom";
import { RobotOutlined, ThunderboltOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { getLlmSettings } from "@/api/settings";
import { fetchStrategies } from "@/api/strategies";
import {
  applyTuningSession,
  getTuningSession,
  startTuningSession,
  tuningAdvise,
  tuningQuickBacktest,
  tuningVerify,
  type TuningAdviseResponse,
  type TuningQuickBacktestResponse,
  type TuningVerifyResponse,
} from "@/api/tuning";
import { listBacktestHistory } from "@/api/backtest";
import BacktestRuntimeFields from "@/components/BacktestRuntimeFields";
import ParamForm from "@/components/ParamForm";
import ParamDisplay from "@/components/ParamDisplay";
import type { TuningBacktestConfig } from "@/api/tuning";
import TradeParamDisplay from "@/components/TradeParamDisplay";
import {
  applyTradeParamsToRuntime,
  backtestScopeLabel,
  DEFAULT_BACKTEST_RUNTIME,
  runtimeFromBacktestTask,
  toBacktestApiPayload,
  tradeParamsFromRuntime,
  type BacktestRuntimeState,
} from "@/lib/backtestRuntime";

const { Title, Paragraph, Text } = Typography;

interface VerifyRound {
  round: number;
  params: Record<string, unknown>;
  tradeParams: Record<string, unknown>;
  backtest: TuningQuickBacktestResponse;
  verify: TuningVerifyResponse;
}

function mergeBacktestWithTrade(
  config: TuningBacktestConfig,
  trade?: Record<string, unknown> | null
): TuningBacktestConfig {
  if (!trade || Object.keys(trade).length === 0) return config;
  return { ...config, ...trade };
}

function buildPriorAnalysis(initial: TuningAdviseResponse, rounds: VerifyRound[]): string {
  let text = initial.analysis;
  for (const r of rounds) {
    text += `\n\n--- 第 ${r.round} 轮检验 ---\n${r.verify.analysis}`;
    if (r.verify.comparison) {
      text += `\n对比：${r.verify.comparison}`;
    }
  }
  return text;
}

function toAdviseFromVerify(
  verify: TuningVerifyResponse,
  params: Record<string, unknown>,
  tradeParams: Record<string, unknown>
): TuningAdviseResponse {
  return {
    analysis: verify.analysis,
    suggested_params: params,
    suggested_trade_params: tradeParams,
    changes: [],
    trade_changes: [],
    risks: verify.risks,
  };
}

function verdictColor(verdict: string, meetsGoal: boolean): string {
  if (meetsGoal || verdict === "达成") return "success";
  if (verdict === "部分达成") return "warning";
  return "error";
}

function BacktestSummaryRow({ summary }: { summary: Record<string, unknown> }) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={12} sm={6}>
        <Statistic title="胜率 %" value={Number(summary.win_rate ?? 0).toFixed(1)} />
      </Col>
      <Col xs={12} sm={6}>
        <Statistic title="夏普" value={Number(summary.sharpe ?? 0).toFixed(2)} />
      </Col>
      <Col xs={12} sm={6}>
        <Statistic title="最大回撤 %" value={Number(summary.max_drawdown_pct ?? 0).toFixed(2)} />
      </Col>
      <Col xs={12} sm={6}>
        <Statistic title="成交笔数" value={Number(summary.total_trades ?? 0)} />
      </Col>
    </Row>
  );
}

export default function TuningPage() {
  const { message, modal } = App.useApp();
  const [searchParams] = useSearchParams();
  const qc = useQueryClient();
  const initialTaskId = searchParams.get("task_id");
  const initialStrategy = searchParams.get("strategy");

  const llmQ = useQuery({ queryKey: ["settings", "llm"], queryFn: getLlmSettings });
  const strategyPackQ = useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
  const historyQ = useQuery({
    queryKey: ["bt-history-tuning"],
    queryFn: () => listBacktestHistory(30),
  });

  const [strategyName, setStrategyName] = useState("breakout_washout");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [goal, setGoal] = useState("在控制回撤的前提下提高夏普与胜率");
  const [taskId, setTaskId] = useState<string | null>(initialTaskId);
  const [btRuntime, setBtRuntime] = useState<BacktestRuntimeState>(DEFAULT_BACKTEST_RUNTIME);
  const [maxIterations, setMaxIterations] = useState(5);
  const [adviseResult, setAdviseResult] = useState<TuningAdviseResponse | null>(null);
  const [initialAdvise, setInitialAdvise] = useState<TuningAdviseResponse | null>(null);
  const [verifyRounds, setVerifyRounds] = useState<VerifyRound[]>([]);
  const [verifyBacktest, setVerifyBacktest] = useState<TuningQuickBacktestResponse | null>(null);
  const [verifyResult, setVerifyResult] = useState<TuningVerifyResponse | null>(null);
  const [tuningSatisfied, setTuningSatisfied] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const strategies = strategyPackQ.data?.strategies;
  const currentStrategy = useMemo(
    () => strategies?.find((s) => s.name === strategyName),
    [strategies, strategyName]
  );

  useEffect(() => {
    if (strategyPackQ.data?.default_strategy && !initialStrategy) {
      setStrategyName(strategyPackQ.data.default_strategy);
    } else if (initialStrategy) {
      setStrategyName(initialStrategy);
    }
  }, [strategyPackQ.data, initialStrategy]);

  useEffect(() => {
    if (currentStrategy?.params_schema) {
      const defaults: Record<string, unknown> = {};
      Object.entries(currentStrategy.params_schema).forEach(([k, v]) => {
        defaults[k] = v.default;
      });
      setParams(defaults);
    }
  }, [currentStrategy?.name, currentStrategy?.params_schema]);

  const sessionQ = useQuery({
    queryKey: ["tuning-session", sessionId],
    queryFn: () => getTuningSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: (q) => {
      const st = q.state.data?.status;
      return st === "running" || st === "pending" ? 2000 : false;
    },
  });

  const baselineSummary = useMemo(() => {
    if (!taskId || !historyQ.data) return null;
    const task = historyQ.data.find((t) => t.id === taskId);
    return (task?.summary as Record<string, unknown> | null) ?? null;
  }, [taskId, historyQ.data]);

  const backtestConfig = useMemo(() => toBacktestApiPayload(btRuntime), [btRuntime]);

  useEffect(() => {
    if (!taskId || !historyQ.data) return;
    const task = historyQ.data.find((t) => t.id === taskId);
    if (!task || task.status !== "done") return;
    setBtRuntime((prev) => runtimeFromBacktestTask(task, prev));
  }, [taskId, historyQ.data]);

  const verifyMut = useMutation({
    mutationFn: (payload: {
      advise: TuningAdviseResponse;
      backtest: TuningQuickBacktestResponse;
      baseline: Record<string, unknown> | null;
      priorRounds: VerifyRound[];
      initial: TuningAdviseResponse;
      tradeParams: Record<string, unknown>;
    }) =>
      tuningVerify({
        strategy: strategyName,
        suggested_params: payload.advise.suggested_params,
        trade_params: payload.tradeParams,
        verify_summary: payload.backtest.summary,
        goal,
        baseline_summary: payload.baseline,
        prior_analysis: buildPriorAnalysis(payload.initial, payload.priorRounds),
      }),
    onSuccess: (data, payload) => {
      const nextParams = data.suggested_params ?? payload.advise.suggested_params;
      const nextTrade =
        data.suggested_trade_params ??
        payload.tradeParams ??
        payload.advise.suggested_trade_params;
      const round: VerifyRound = {
        round: payload.priorRounds.length + 1,
        params: nextParams,
        tradeParams: nextTrade,
        backtest: payload.backtest,
        verify: data,
      };
      setVerifyRounds((prev) => [...prev, round]);
      setVerifyResult(data);
      setVerifyBacktest(payload.backtest);
      setBtRuntime((rt) => applyTradeParamsToRuntime(rt, nextTrade));
      setAdviseResult(toAdviseFromVerify(data, nextParams, nextTrade));
      message.success(`第 ${round.round} 轮 AI 检验完成`);
      promptContinueTuning(data, nextParams, nextTrade, round.round);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const quickBacktestMut = useMutation({
    mutationFn: (payload: {
      advise: TuningAdviseResponse;
      params: Record<string, unknown>;
      priorRounds: VerifyRound[];
      initial: TuningAdviseResponse;
      backtestConfigOverride?: TuningBacktestConfig;
    }) => {
      const cfg = mergeBacktestWithTrade(
        payload.backtestConfigOverride ?? backtestConfig,
        payload.advise.suggested_trade_params
      );
      return tuningQuickBacktest({
        strategy: strategyName,
        params: payload.params,
        backtest_config: cfg,
      }).then((data) => ({
        data,
        advise: payload.advise,
        priorRounds: payload.priorRounds,
        initial: payload.initial,
        tradeParams: tradeParamsFromRuntime(
          applyTradeParamsToRuntime(btRuntime, payload.advise.suggested_trade_params ?? {})
        ),
      }));
    },
    onSuccess: ({ data, advise, priorRounds, initial, tradeParams }) => {
      setVerifyBacktest(data);
      message.success(`验证回测完成，用时 ${data.elapsed_seconds}s，正在提交 AI 检验…`);
      verifyMut.mutate({ advise, backtest: data, baseline: baselineSummary, priorRounds, initial, tradeParams });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const startVerifyBacktest = (
    advise: TuningAdviseResponse,
    options?: { resetRounds?: boolean; initial?: TuningAdviseResponse }
  ) => {
    const initial = options?.initial ?? initialAdvise ?? advise;
    if (options?.resetRounds) {
      setVerifyRounds([]);
      setTuningSatisfied(false);
      setInitialAdvise(initial);
    }
    setVerifyBacktest(null);
    setVerifyResult(null);
    quickBacktestMut.mutate({
      advise,
      params: advise.suggested_params,
      priorRounds: options?.resetRounds ? [] : verifyRounds,
      initial,
    });
  };

  const promptContinueTuning = (
    verify: TuningVerifyResponse,
    nextParams: Record<string, unknown>,
    nextTrade: Record<string, unknown>,
    round: number
  ) => {
    if (tuningSatisfied) return;

    const hasTweak = !!(verify.suggested_params || verify.suggested_trade_params);
    const title = hasTweak
      ? `是否用第 ${round} 轮微调参数再次回测？`
      : verify.meets_goal
        ? "目标已达成，是否结束调参？"
        : "尚未完全达成目标";

    const applySatisfied = () => {
      setTuningSatisfied(true);
      setParams(nextParams);
      setBtRuntime((rt) => applyTradeParamsToRuntime(rt, nextTrade));
    };

    if (hasTweak) {
      modal.confirm({
        title,
        content: (
          <div>
            <p style={{ marginBottom: 8 }}>
              检验结论：<Tag color={verdictColor(verify.verdict, verify.meets_goal)}>{verify.verdict}</Tag>
            </p>
            <p style={{ marginBottom: 8 }}>
              {verify.analysis.slice(0, 200)}
              {verify.analysis.length > 200 ? "…" : ""}
            </p>
            <p style={{ marginBottom: 0 }}>
              确认后将用 AI 微调的策略参数与交易参数（止盈/止损/持仓等）再次回测并检验。
            </p>
          </div>
        ),
        okText: "继续回测验证",
        cancelText: "结果已满意",
        onOk: () => {
          const nextAdvise = toAdviseFromVerify(
            verify,
            verify.suggested_params ?? nextParams,
            verify.suggested_trade_params ?? nextTrade
          );
          startVerifyBacktest(nextAdvise);
        },
        onCancel: () => {
          applySatisfied();
          message.success("已标记为满意，参数已应用到表单与回测配置");
        },
      });
      return;
    }

    if (verify.meets_goal) {
      modal.confirm({
        title,
        content: "当前结果已满足调参目标。若需继续优化，可重新获取顾问建议。",
        okText: "结束调参",
        cancelText: "重新获取建议",
        onOk: () => {
          applySatisfied();
          message.success("调参完成，参数已应用到表单与回测配置");
        },
        onCancel: () => {
          adviseMut.mutate();
        },
      });
      return;
    }

    modal.confirm({
      title,
      content: "AI 未给出新的微调参数。可重新获取顾问建议（基于最近回测结果），或结束本轮调参。",
      okText: "重新获取建议",
      cancelText: "结束调参",
      onOk: () => adviseMut.mutate(),
      onCancel: () => setTuningSatisfied(true),
    });
  };

  const promptVerifyBacktest = (advise: TuningAdviseResponse, initial?: TuningAdviseResponse) => {
    modal.confirm({
      title: verifyRounds.length > 0 ? "是否再次回测验证？" : "是否用建议参数回测一次？",
      content: (
        <div>
          <p style={{ marginBottom: 8 }}>
            将使用当前回测配置（{backtestScopeLabel(btRuntime)}，{backtestConfig.start_date} ~{" "}
            {backtestConfig.end_date}）运行一次回测。
          </p>
          <p style={{ marginBottom: 0 }}>
            回测完成后会自动提交 AI 检验；若 AI 给出微调参数，可继续迭代直至满意。
          </p>
        </div>
      ),
      okText: "开始回测验证",
      cancelText: "稍后再说",
      onOk: () =>
        startVerifyBacktest(advise, {
          resetRounds: verifyRounds.length === 0,
          initial: initial ?? advise,
        }),
    });
  };

  const adviseMut = useMutation({
    mutationFn: () => {
      const latestSummary = verifyBacktest?.summary ?? baselineSummary ?? undefined;
      return tuningAdvise({
        strategy: strategyName,
        params: adviseResult?.suggested_params ?? params,
        goal,
        task_id: verifyRounds.length > 0 ? null : taskId,
        summary: verifyRounds.length > 0 ? latestSummary : undefined,
        backtest_config: backtestConfig,
      });
    },
    onSuccess: (data) => {
      setAdviseResult(data);
      setInitialAdvise(data);
      setVerifyRounds([]);
      setVerifyBacktest(null);
      setVerifyResult(null);
      setTuningSatisfied(false);
      setBtRuntime((rt) => applyTradeParamsToRuntime(rt, data.suggested_trade_params ?? {}));
      message.success("顾问分析完成");
      promptVerifyBacktest(data, data);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const sessionMut = useMutation({
    mutationFn: () =>
      startTuningSession({
        strategy: strategyName,
        goal,
        params,
        objective: "composite",
        max_iterations: maxIterations,
        backtest_config: backtestConfig,
      }),
    onSuccess: (data) => {
      setSessionId(data.session_id);
      message.success("自动调参已启动");
    },
    onError: (e: Error) => message.error(e.message),
  });

  const applyMut = useMutation({
    mutationFn: () => applyTuningSession(sessionId!),
    onSuccess: () => {
      message.success("已应用为策略默认参数");
      qc.invalidateQueries({ queryKey: ["strategies"] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const llmReady = llmQ.data?.configured;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card>
        <Space align="start">
          <RobotOutlined style={{ fontSize: 28, color: "#722ed1" }} />
          <div>
            <Title level={4} style={{ margin: 0 }}>
              AI 参数调优
            </Title>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              大模型分析回测结果并建议策略参数；可选多轮自动回测迭代。请先配置
              <Link to="/settings/llm"> 大模型提供商</Link>。
            </Paragraph>
          </div>
        </Space>
      </Card>

      {!llmReady && !llmQ.isLoading && (
        <Alert
          type="warning"
          showIcon
          message="未配置大模型"
          description={<Link to="/settings/llm">前往系统设置 → 大模型提供商</Link>}
        />
      )}

      <Card title="调参配置">
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}>
            <Text type="secondary">策略</Text>
            <Select
              style={{ width: "100%", marginTop: 4 }}
              value={strategyName}
              onChange={setStrategyName}
              options={(strategies ?? []).map((s) => ({ label: s.label, value: s.name }))}
            />
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary">参考回测任务（可选）</Text>
            <Select
              allowClear
              style={{ width: "100%", marginTop: 4 }}
              placeholder="选择历史回测（同步回测配置）"
              value={taskId}
              onChange={setTaskId}
              options={(historyQ.data ?? [])
                .filter((t) => t.status === "done")
                .map((t) => ({
                  label: `${t.name || t.id.slice(0, 8)} · ${t.strategy_name} · ${t.trade_count}笔`,
                  value: t.id,
                }))}
            />
          </Col>
          <Col span={24}>
            <Text type="secondary">调参目标</Text>
            <Input.TextArea
              rows={2}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              style={{ marginTop: 4 }}
            />
          </Col>
        </Row>
        {currentStrategy && (
          <div style={{ marginTop: 16 }}>
            <ParamForm schema={currentStrategy.params_schema} value={params} onChange={setParams} />
          </div>
        )}
      </Card>

      <Card
        title="回测配置"
        extra={<Tag>{backtestScopeLabel(btRuntime)}</Tag>}
      >
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>
          与导航「回测」页使用同一套引擎参数；AI 调参可同时优化止盈/止损/持仓/仓位等交易参数。默认全市场扫描。
        </Paragraph>
        <BacktestRuntimeFields value={btRuntime} onChange={setBtRuntime} />
      </Card>

      <Card title="顾问分析">
        <Space wrap>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={adviseMut.isPending}
            disabled={!llmReady}
            onClick={() => adviseMut.mutate()}
          >
            获取调参建议
          </Button>
          {adviseResult && (
            <Button
              onClick={() => {
                setParams(adviseResult.suggested_params);
                setBtRuntime((rt) => applyTradeParamsToRuntime(rt, adviseResult.suggested_trade_params ?? {}));
              }}
            >
              应用到表单与回测配置
            </Button>
          )}
        </Space>
        {adviseMut.isPending && <Spin style={{ display: "block", marginTop: 16 }} />}
        {adviseResult && (
          <Space direction="vertical" style={{ width: "100%", marginTop: 16 }}>
            <Alert type="info" message={adviseResult.analysis} />
            {adviseResult.risks.length > 0 && (
              <Alert type="warning" message={`风险提示：${adviseResult.risks.join("；")}`} />
            )}
            <Text strong>建议策略参数</Text>
            <ParamDisplay schema={currentStrategy?.params_schema} params={adviseResult.suggested_params} />
            {adviseResult.suggested_trade_params && (
              <>
                <Text strong>建议交易参数（止盈/止损/持仓/仓位）</Text>
                <TradeParamDisplay params={adviseResult.suggested_trade_params} />
              </>
            )}
          </Space>
        )}
      </Card>

      {(adviseResult || verifyBacktest || verifyResult || verifyRounds.length > 0) && (
        <Card
          title={
            <Space>
              <span>验证回测与 AI 检验</span>
              {verifyRounds.length > 0 && <Tag color="processing">已进行 {verifyRounds.length} 轮</Tag>}
              {tuningSatisfied && <Tag color="success">已满意</Tag>}
            </Space>
          }
          extra={
            adviseResult && !quickBacktestMut.isPending && !verifyMut.isPending ? (
              <Space wrap>
                {(verifyResult?.suggested_params || verifyResult?.suggested_trade_params) && !tuningSatisfied && (
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    onClick={() =>
                      promptContinueTuning(
                        verifyResult,
                        verifyResult.suggested_params ?? adviseResult.suggested_params,
                        verifyResult.suggested_trade_params ?? adviseResult.suggested_trade_params,
                        verifyRounds.length
                      )
                    }
                  >
                    用微调参数继续验证
                  </Button>
                )}
                <Button
                  icon={<ThunderboltOutlined />}
                  onClick={() => promptVerifyBacktest(adviseResult, initialAdvise ?? adviseResult)}
                >
                  再次回测验证
                </Button>
                {!tuningSatisfied && verifyRounds.length > 0 && (
                  <Button
                    onClick={() => {
                      setTuningSatisfied(true);
                      setParams(adviseResult.suggested_params);
                      setBtRuntime((rt) =>
                        applyTradeParamsToRuntime(rt, adviseResult.suggested_trade_params ?? {})
                      );
                      message.success("已标记为满意，参数已应用到表单与回测配置");
                    }}
                  >
                    结果已满意
                  </Button>
                )}
              </Space>
            ) : null
          }
        >
          {(quickBacktestMut.isPending || verifyMut.isPending) && (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Spin />
              <Text type="secondary">
                {quickBacktestMut.isPending
                  ? "正在用建议参数运行回测，可能需要数分钟…"
                  : "回测完成，AI 正在检验结果…"}
              </Text>
            </Space>
          )}

          {verifyBacktest && !quickBacktestMut.isPending && (
            <Space direction="vertical" style={{ width: "100%" }} size="middle">
              <Descriptions size="small" bordered column={3}>
                <Descriptions.Item label="综合得分">{verifyBacktest.score.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="回测用时">{verifyBacktest.elapsed_seconds}s</Descriptions.Item>
                <Descriptions.Item label="扫描范围">{backtestScopeLabel(btRuntime)}</Descriptions.Item>
                <Descriptions.Item label="区间">
                  {backtestConfig.start_date} ~ {backtestConfig.end_date}
                </Descriptions.Item>
              </Descriptions>
              <BacktestSummaryRow summary={verifyBacktest.summary} />
            </Space>
          )}

          {verifyResult && (
            <Space direction="vertical" style={{ width: "100%", marginTop: 16 }} size="middle">
              <Space wrap>
                <Tag color={verdictColor(verifyResult.verdict, verifyResult.meets_goal)}>
                  {verifyResult.verdict}
                </Tag>
                {verifyResult.meets_goal ? (
                  <Tag color="success">达成目标</Tag>
                ) : (
                  <Tag color="default">未完全达成</Tag>
                )}
              </Space>
              <Alert type="info" message="AI 检验结论" description={verifyResult.analysis} />
              {verifyResult.comparison && (
                <Alert type="success" message="与基线对比" description={verifyResult.comparison} />
              )}
              {verifyResult.highlights.length > 0 && (
                <Alert type="info" message={`关键发现：${verifyResult.highlights.join("；")}`} />
              )}
              {verifyResult.risks.length > 0 && (
                <Alert type="warning" message={`风险提示：${verifyResult.risks.join("；")}`} />
              )}
              {(verifyResult.suggested_params || verifyResult.suggested_trade_params) && !tuningSatisfied && (
                <>
                  <Text strong>AI 建议进一步微调（可继续迭代）：</Text>
                  {verifyResult.suggested_params && (
                    <ParamDisplay
                      schema={currentStrategy?.params_schema}
                      params={verifyResult.suggested_params}
                    />
                  )}
                  {verifyResult.suggested_trade_params && (
                    <TradeParamDisplay
                      title="交易参数"
                      params={verifyResult.suggested_trade_params}
                    />
                  )}
                  <Space wrap>
                    <Button
                      type="primary"
                      icon={<ThunderboltOutlined />}
                      onClick={() =>
                        promptContinueTuning(
                          verifyResult,
                          verifyResult.suggested_params ?? adviseResult!.suggested_params,
                          verifyResult.suggested_trade_params ?? adviseResult!.suggested_trade_params,
                          verifyRounds.length
                        )
                      }
                    >
                      用微调参数回测验证
                    </Button>
                    <Button
                      onClick={() => {
                        if (verifyResult.suggested_params) {
                          setParams(verifyResult.suggested_params);
                        }
                        if (verifyResult.suggested_trade_params) {
                          setBtRuntime((rt) =>
                            applyTradeParamsToRuntime(rt, verifyResult.suggested_trade_params!)
                          );
                        }
                      }}
                    >
                      应用到表单与回测配置
                    </Button>
                  </Space>
                </>
              )}
            </Space>
          )}

          {verifyRounds.length > 0 && (
            <Table
              style={{ marginTop: 16 }}
              rowKey="round"
              size="small"
              pagination={false}
              title={() => <Text strong>迭代历史</Text>}
              dataSource={verifyRounds}
              columns={[
                { title: "轮次", dataIndex: "round", width: 60 },
                {
                  title: "检验结论",
                  render: (_, r) => (
                    <Tag color={verdictColor(r.verify.verdict, r.verify.meets_goal)}>{r.verify.verdict}</Tag>
                  ),
                },
                {
                  title: "得分",
                  render: (_, r) => r.backtest.score.toFixed(2),
                },
                {
                  title: "胜率%",
                  render: (_, r) => Number(r.backtest.summary.win_rate ?? 0).toFixed(1),
                },
                {
                  title: "夏普",
                  render: (_, r) => Number(r.backtest.summary.sharpe ?? 0).toFixed(2),
                },
                {
                  title: "耗时s",
                  render: (_, r) => r.backtest.elapsed_seconds,
                },
                {
                  title: "操作",
                  render: (_, r) => (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => setParams(r.params)}
                    >
                      应用此轮参数
                    </Button>
                  ),
                },
              ]}
            />
          )}

          {adviseResult && verifyRounds.length === 0 && !verifyBacktest && !quickBacktestMut.isPending && !verifyMut.isPending && (
            <Alert
              type="info"
              showIcon
              message="尚未验证"
              description='点击右上角「用建议参数回测验证」，或在获取建议时选择「开始回测验证」。'
            />
          )}
        </Card>
      )}

      <Card
        title="自动循环调参"
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            每轮：回测 → AI 检验 → 按检验建议优化；达成目标提前结束，否则最多 {maxIterations} 轮
          </Text>
        }
      >
        <Space wrap style={{ marginBottom: 16 }}>
          <span>最大轮次</span>
          <InputNumber min={1} max={500} value={maxIterations} onChange={(v) => setMaxIterations(v ?? 5)} />
          <Button
            loading={sessionMut.isPending}
            disabled={!llmReady}
            onClick={() => sessionMut.mutate()}
          >
            启动自动调参
          </Button>
          {sessionQ.data?.status === "done" && sessionQ.data.best_trial_id && (
            <Button type="primary" loading={applyMut.isPending} onClick={() => applyMut.mutate()}>
              应用最优参数为默认
            </Button>
          )}
        </Space>
        {sessionQ.isLoading && sessionId && <Spin />}
        {sessionQ.data && (
          <>
            <Tag color={sessionQ.data.status === "done" ? "success" : "processing"}>
              {sessionQ.data.status}
            </Tag>
            {sessionQ.data.error && <Alert type="error" message={sessionQ.data.error} style={{ marginTop: 8 }} />}
            <Table
              style={{ marginTop: 12 }}
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={sessionQ.data.trials}
              rowClassName={(r) => (r.id === sessionQ.data?.best_trial_id ? "ant-table-row-selected" : "")}
              columns={[
                { title: "轮次", dataIndex: "iteration", width: 60 },
                {
                  title: "检验",
                  width: 88,
                  render: (_, r) => {
                    const m = r.llm_analysis?.match(/^\[(.+?)\]/);
                    const verdict = m?.[1] ?? "—";
                    const ok = verdict === "达成" || r.llm_analysis?.includes("达成");
                    return (
                      <Tag color={ok ? "success" : verdict === "部分达成" ? "warning" : "default"}>
                        {verdict}
                      </Tag>
                    );
                  },
                },
                {
                  title: "得分",
                  dataIndex: "score",
                  render: (v: number | null) => (v != null ? v.toFixed(2) : "—"),
                },
                {
                  title: "胜率%",
                  render: (_, r) => {
                    const v = r.summary?.win_rate as number | undefined;
                    return v != null ? v.toFixed(1) : "—";
                  },
                },
                {
                  title: "夏普",
                  render: (_, r) => {
                    const v = r.summary?.sharpe as number | undefined;
                    return v != null ? v.toFixed(2) : "—";
                  },
                },
                {
                  title: "成交",
                  render: (_, r) => r.summary?.total_trades ?? "—",
                },
                {
                  title: "AI 检验摘要",
                  ellipsis: true,
                  render: (_, r) => {
                    const text = r.llm_analysis?.replace(/^\[[^\]]+\]\s*/, "") ?? "—";
                    return text.length > 48 ? `${text.slice(0, 48)}…` : text;
                  },
                },
                {
                  title: "耗时s",
                  dataIndex: "elapsed_seconds",
                },
              ]}
            />
          </>
        )}
      </Card>
    </Space>
  );
}
