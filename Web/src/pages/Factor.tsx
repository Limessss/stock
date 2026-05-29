import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Card,
  Col,
  Empty,
  Radio,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { FundOutlined, ReloadOutlined } from "@ant-design/icons";

import {
  getFactorAnalysis,
  type FactorAnalysisResponse,
  type FactorICRow,
} from "@/api/factor";
import { listBacktestHistory } from "@/api/backtest";
import FactorQuantileHeatmap from "@/components/FactorQuantileHeatmap";

const { Title, Text } = Typography;

type Target = "return_pct" | "max_up_pct";
type HeatmapMetric = "mean" | "win_rate" | "big_win_rate";

export default function FactorPage() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [target, setTarget] = useState<Target>("return_pct");
  const [quantileN, setQuantileN] = useState<number>(5);
  const [heatmapMetric, setHeatmapMetric] = useState<HeatmapMetric>("mean");

  const historyQ = useQuery({
    queryKey: ["bt-history-factor"],
    queryFn: () => listBacktestHistory(50),
    staleTime: 30_000,
  });

  // 默认选第一个 trades>50 的 done 任务
  const candidates = useMemo(
    () => (historyQ.data ?? []).filter((t) => t.status === "done" && t.trade_count >= 30),
    [historyQ.data]
  );
  const effectiveTaskId = taskId ?? candidates[0]?.id ?? null;

  const analysisQ = useQuery({
    queryKey: ["factor-analysis", effectiveTaskId, target, quantileN],
    queryFn: () => getFactorAnalysis(effectiveTaskId!, { target, quantileN: quantileN }),
    enabled: !!effectiveTaskId,
  });

  const data: FactorAnalysisResponse | undefined = analysisQ.data;
  const sortedIc = useMemo(
    () =>
      [...(data?.ic ?? [])].sort(
        (a, b) => Math.abs(b.ic_return ?? 0) - Math.abs(a.ic_return ?? 0)
      ),
    [data?.ic]
  );

  const topFactors = useMemo(
    () => sortedIc.slice(0, 8).map((r) => r.field),
    [sortedIc]
  );
  const heatmapFactors = useMemo(() => {
    if (!data?.quantiles) return [];
    // 按 IC 排序后，把 |IC| 最大的因子排在最前
    const order = sortedIc.map((r) => r.field);
    return [...data.quantiles].sort(
      (a, b) => order.indexOf(a.field) - order.indexOf(b.field)
    );
  }, [data?.quantiles, sortedIc]);

  return (
    <>
      <Title level={3} style={{ marginTop: 0 }}>
        <FundOutlined /> 多因子分析
      </Title>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col span={8}>
            <Text type="secondary">回测任务</Text>
            <Select
              value={effectiveTaskId ?? undefined}
              onChange={setTaskId}
              loading={historyQ.isLoading}
              style={{ width: "100%" }}
              placeholder="选择已完成的回测任务"
              optionLabelProp="label"
            >
              {candidates.map((t) => (
                <Select.Option
                  key={t.id}
                  value={t.id}
                  label={`${t.name || t.id.slice(0, 8)} · ${t.trade_count}笔`}
                >
                  <Space>
                    <Text strong>{t.name || t.id.slice(0, 8)}</Text>
                    <Tag color="blue">{t.trade_count} 笔</Tag>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {t.start_date} → {t.end_date}
                    </Text>
                    {t.summary && (
                      <Text
                        style={{
                          color: t.summary.win_rate >= 50 ? "#3f8600" : "#cf1322",
                          fontSize: 11,
                        }}
                      >
                        胜率 {t.summary.win_rate.toFixed(1)}%
                      </Text>
                    )}
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Col>
          <Col span={6}>
            <Text type="secondary">目标变量</Text>
            <br />
            <Radio.Group value={target} onChange={(e) => setTarget(e.target.value)}>
              <Radio.Button value="return_pct">单笔收益 %</Radio.Button>
              <Radio.Button value="max_up_pct">最大上涨 %</Radio.Button>
            </Radio.Group>
          </Col>
          <Col span={4}>
            <Text type="secondary">分位数</Text>
            <br />
            <Select
              value={quantileN}
              onChange={setQuantileN}
              style={{ width: 100 }}
              options={[3, 5, 10].map((n) => ({ value: n, label: `${n} 分位` }))}
            />
          </Col>
          <Col span={6}>
            <Text type="secondary">热力图数值</Text>
            <br />
            <Radio.Group
              value={heatmapMetric}
              onChange={(e) => setHeatmapMetric(e.target.value)}
            >
              <Radio.Button value="mean">平均</Radio.Button>
              <Radio.Button value="win_rate">胜率</Radio.Button>
              <Radio.Button value="big_win_rate">大赚率</Radio.Button>
            </Radio.Group>
          </Col>
        </Row>
      </Card>

      {!effectiveTaskId && (
        <Alert
          type="info"
          showIcon
          message="还没有可分析的回测任务"
          description="请先在『回测』页跑一个回测（建议 trades ≥ 100），完成后回到这里。"
        />
      )}

      {analysisQ.isError && (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={(analysisQ.error as Error).message}
        />
      )}

      {data && (
        <>
          <Card style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title="样本笔数" value={data.total_trades} />
              </Col>
              <Col span={6}>
                <Statistic
                  title="最强正向因子"
                  value={
                    sortedIc.find((r) => (r.ic_return ?? 0) > 0)?.label ?? "-"
                  }
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="最强反向因子"
                  value={
                    sortedIc.find((r) => (r.ic_return ?? 0) < 0)?.label ?? "-"
                  }
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="|IC| 最大值"
                  value={Math.abs(sortedIc[0]?.ic_return ?? 0)}
                  precision={4}
                />
              </Col>
            </Row>
          </Card>

          <Card title="IC 表（Spearman 秩相关系数）" style={{ marginBottom: 16 }}>
            <ICTable rows={sortedIc} highlight={topFactors} />
          </Card>

          <Card
            title={
              <Space>
                <span>因子 × 分位 收益结构</span>
                <Tag color="blue">{heatmapMetric === "mean" ? "平均收益" : heatmapMetric === "win_rate" ? "胜率" : "大赚率"}</Tag>
              </Space>
            }
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                <ReloadOutlined /> 因子按 |IC| 降序排列；点击格子查看明细
              </Text>
            }
            style={{ marginBottom: 16 }}
          >
            {heatmapFactors.length > 0 ? (
              <FactorQuantileHeatmap
                factors={heatmapFactors}
                metric={heatmapMetric}
                height={Math.max(300, heatmapFactors.length * 32)}
              />
            ) : (
              <Empty description="该任务无可分析因子" />
            )}
          </Card>

          <Card title="阅读指南">
            <ul style={{ marginBottom: 0, lineHeight: 1.8 }}>
              <li>
                <Text strong>IC（信息系数）</Text>：因子值排名 vs 收益排名的 Spearman 相关。
                |IC| ≥ 0.05 即视为有较强预测力；正 IC 表示因子值越大收益越好（应取高分位），
                负 IC 表示因子值越小收益越好（应取低分位）。
              </li>
              <li>
                <Text strong>分位单调性</Text>：理想因子的 Q1→Q5 收益应单调上升或下降；
                若中段收益最高（如 Q3 峰值），说明该因子的极端值反而带噪音。
              </li>
              <li>
                <Text strong>大赚率</Text>：单笔 ≥ 20% 占比；用于挑"赔率优势"显著的分位段。
              </li>
            </ul>
          </Card>
        </>
      )}
    </>
  );
}

function ICTable({
  rows,
  highlight,
}: {
  rows: FactorICRow[];
  highlight: string[];
}) {
  const columns = [
    {
      title: "因子",
      dataIndex: "label",
      render: (v: string, r: FactorICRow) => (
        <Space>
          <Text strong>{v}</Text>
          {highlight.slice(0, 3).includes(r.field) && (
            <Tag color="gold">TOP</Tag>
          )}
        </Space>
      ),
    },
    {
      title: "字段",
      dataIndex: "field",
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: "IC (单笔收益)",
      dataIndex: "ic_return",
      render: (v: number | null) => <ICCell value={v} />,
      sorter: (a: FactorICRow, b: FactorICRow) =>
        Math.abs(b.ic_return ?? 0) - Math.abs(a.ic_return ?? 0),
    },
    {
      title: "IC (最大上涨)",
      dataIndex: "ic_max_up",
      render: (v: number | null) => <ICCell value={v} />,
      sorter: (a: FactorICRow, b: FactorICRow) =>
        Math.abs(b.ic_max_up ?? 0) - Math.abs(a.ic_max_up ?? 0),
    },
    {
      title: "方向",
      key: "dir",
      render: (_: unknown, r: FactorICRow) => {
        const ic = r.ic_return ?? 0;
        if (Math.abs(ic) < 0.02) return <Tag>弱</Tag>;
        return ic > 0 ? <Tag color="green">正向（取高分位）</Tag> : <Tag color="red">反向（取低分位）</Tag>;
      },
    },
  ];
  return (
    <Table
      rowKey="field"
      dataSource={rows}
      columns={columns}
      pagination={false}
      size="small"
    />
  );
}

function ICCell({ value }: { value: number | null }) {
  if (value == null || isNaN(value)) return <Text type="secondary">—</Text>;
  const abs = Math.abs(value);
  let color = "#999";
  if (abs >= 0.1) color = value > 0 ? "#3f8600" : "#cf1322";
  else if (abs >= 0.05) color = value > 0 ? "#52c41a" : "#fa541c";
  else if (abs >= 0.02) color = value > 0 ? "#73d13d" : "#fa8c16";
  return (
    <Text style={{ color, fontFamily: "monospace", fontWeight: 600 }}>
      {value > 0 ? "+" : ""}
      {value.toFixed(4)}
    </Text>
  );
}
