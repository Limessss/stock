import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { SearchOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { useSearchParams } from "react-router-dom";

import { getDiagnose, getKline } from "@/api/diagnose";
import { fetchStrategies } from "@/api/strategies";
import KlineChart, { type KlineMarker } from "@/components/KlineChart";
import ParamForm from "@/components/ParamForm";
import RulesTable from "@/components/RulesTable";

const { Title, Text } = Typography;

function findProbeDate(rules: { name: string; value: unknown }[]): string | null {
  const probeRule = rules.find(
    (r) => r.name === "洗盘高点定位" || r.name === "试盘高点定位"
  );
  if (probeRule && typeof probeRule.value === "string") {
    const m = probeRule.value.match(/(\d{4}-\d{2}-\d{2})/);
    if (m) return m[1];
  }
  return null;
}

export default function DiagnosePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialCode = searchParams.get("code") ?? "";
  const initialDate = searchParams.get("date");
  const initialStrategy = searchParams.get("strategy");

  const [code, setCode] = useState<string>(initialCode);
  const [date, setDate] = useState<Dayjs | null>(
    initialDate ? dayjs(initialDate) : null
  );
  const [strategyName, setStrategyName] = useState<string>(initialStrategy ?? "breakout_washout");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [queryKeyToken, setQueryKeyToken] = useState<number>(initialCode ? Date.now() : 0);

  const { data: strategyPack } = useQuery({
    queryKey: ["strategies"],
    queryFn: fetchStrategies,
    staleTime: 30_000,
  });
  const strategies = strategyPack?.strategies;

  useEffect(() => {
    if (initialStrategy || !strategyPack) return;
    setStrategyName(strategyPack.default_strategy);
  }, [initialStrategy, strategyPack]);

  const currentStrategy = useMemo(
    () => strategies?.find((s) => s.name === strategyName),
    [strategies, strategyName]
  );

  const enabled = queryKeyToken > 0 && code.length > 0;
  const dateStr = date ? date.format("YYYY-MM-DD") : undefined;

  const diagnoseQ = useQuery({
    queryKey: ["diagnose", code.toUpperCase(), dateStr, strategyName, params, queryKeyToken],
    queryFn: () =>
      getDiagnose(code.toUpperCase(), {
        date: dateStr,
        strategy: strategyName,
        params,
      }),
    enabled,
    retry: false,
  });

  const probeDateForKline = diagnoseQ.data ? findProbeDate(diagnoseQ.data.rules) : null;
  const klineCenterDate = dateStr ?? diagnoseQ.data?.date;

  const klineQ = useQuery({
    queryKey: ["kline", code.toUpperCase(), klineCenterDate, probeDateForKline, queryKeyToken],
    queryFn: () =>
      getKline(code.toUpperCase(), {
        lastN: 160,
        centerDate: klineCenterDate,
        minDate: probeDateForKline ?? undefined,
      }),
    enabled: enabled && !!klineCenterDate,
    retry: false,
  });

  const markers = useMemo<KlineMarker[]>(() => {
    const out: KlineMarker[] = [];
    if (diagnoseQ.data) {
      out.push({
        time: diagnoseQ.data.date,
        position: "aboveBar",
        color: diagnoseQ.data.final_status === "pass" ? "#cf1322" : "#666",
        shape: "arrowDown",
        text: diagnoseQ.data.final_status === "pass" ? "信号" : "未命中",
      });
      const probeDate = findProbeDate(diagnoseQ.data.rules);
      if (probeDate) {
        out.push({
          time: probeDate,
          position: "belowBar",
          color: "#1677ff",
          shape: "circle",
          text: "试盘日",
        });
      }
    }
    return out.sort((a, b) => a.time.localeCompare(b.time));
  }, [diagnoseQ.data]);

  const onSubmit = () => {
    if (!code.trim()) return;
    setSearchParams({
      code: code.trim().toUpperCase(),
      date: dateStr ?? "",
      strategy: strategyName,
    });
    setQueryKeyToken(Date.now());
  };

  useEffect(() => {
    if (initialCode) onSubmit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <Title level={3} style={{ marginTop: 0 }}>
        个股诊断
      </Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        按所选策略逐条评估规则，支持洗盘突破与起爆点；K 线图为通用展示。
      </Text>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col>
            <Text>代码</Text>
            <Input
              value={code}
              placeholder="如 SZ002281"
              onChange={(e) => setCode(e.target.value)}
              onPressEnter={onSubmit}
              style={{ width: 220 }}
            />
          </Col>
          <Col>
            <Text>日期</Text>
            <DatePicker
              value={date}
              onChange={setDate}
              placeholder="留空=最后一日"
              format="YYYY-MM-DD"
              style={{ width: 160 }}
            />
          </Col>
          <Col>
            <Text>策略</Text>
            <Select
              value={strategyName}
              onChange={(v) => {
                setStrategyName(v);
                setParams({});
              }}
              options={(strategies ?? []).map((s) => ({ label: s.label, value: s.name }))}
              style={{ width: 160 }}
            />
          </Col>
          <Col style={{ display: "flex", alignItems: "flex-end" }}>
            <Button type="primary" icon={<SearchOutlined />} onClick={onSubmit}>
              诊断
            </Button>
          </Col>
        </Row>

        {currentStrategy && (
          <>
            <Divider style={{ margin: "16px 0" }} orientation="left" orientationMargin="0">
              策略参数
            </Divider>
            <ParamForm
              schema={currentStrategy.params_schema}
              value={params}
              onChange={setParams}
            />
          </>
        )}
      </Card>

      {diagnoseQ.isLoading && (
        <Card>
          <Spin spinning tip="正在诊断…">
            <div style={{ minHeight: 80 }} />
          </Spin>
        </Card>
      )}

      {diagnoseQ.error && (
        <Alert
          type="error"
          message="诊断失败"
          description={(diagnoseQ.error as Error).message}
          showIcon
        />
      )}

      {diagnoseQ.data && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Card>
            <Row gutter={16}>
              <Col span={5}>
                <Statistic
                  title={diagnoseQ.data.name ? `代码 · ${diagnoseQ.data.name}` : "代码"}
                  value={diagnoseQ.data.code}
                  valueStyle={{ fontSize: 24 }}
                />
              </Col>
              <Col span={5}>
                <Statistic title="策略" value={diagnoseQ.data.strategy_label || strategyName} />
              </Col>
              <Col span={4}>
                <Statistic title="日期" value={diagnoseQ.data.date} valueStyle={{ fontSize: 18 }} />
              </Col>
              <Col span={4}>
                <Statistic
                  title="收盘价"
                  value={diagnoseQ.data.close}
                  precision={2}
                  valueStyle={{ fontSize: 18 }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="最终判定"
                  value={diagnoseQ.data.final_status.toUpperCase()}
                  valueStyle={{
                    fontSize: 22,
                    color: diagnoseQ.data.final_status === "pass" ? "#3f8600" : "#cf1322",
                  }}
                  suffix={
                    diagnoseQ.data.score !== null ? (
                      <Tag color="purple" style={{ marginLeft: 8 }}>
                        评分 {diagnoseQ.data.score.toFixed(2)}
                      </Tag>
                    ) : null
                  }
                />
              </Col>
            </Row>
          </Card>

          <Card title="K 线（含试盘日 / 信号日标记）" size="small">
            {klineQ.isLoading ? (
              <Spin spinning>
                <div style={{ minHeight: 560 }} />
              </Spin>
            ) : klineQ.data && klineCenterDate ? (
              <KlineChart
                data={klineQ.data}
                markers={markers}
                height={560}
                focusDate={klineCenterDate}
                visibleBars={100}
              />
            ) : (
              <Alert type="warning" message="无 K 线数据" />
            )}
          </Card>

          <Card title="技术指标快照" size="small">
            <Descriptions column={4} size="small" bordered>
              {Object.entries(diagnoseQ.data.indicators).map(([k, v]) => (
                <Descriptions.Item key={k} label={k.toUpperCase()}>
                  {v === null ? "-" : v}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </Card>

          <Card title={`规则评估（共 ${diagnoseQ.data.rules.length} 条）`} size="small">
            <RulesTable rules={diagnoseQ.data.rules} />
          </Card>
        </Space>
      )}
    </>
  );
}
