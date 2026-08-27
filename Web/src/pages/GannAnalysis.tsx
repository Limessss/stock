import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "@/components/ui";
import { RedoOutlined, SearchOutlined } from "@/components/ui/icons";
import dayjs, { type Dayjs } from "dayjs";
import { useSearchParams } from "react-router-dom";

import { getGannAnalysis } from "@/api/gann";
import { getKline } from "@/api/kline";
import ChineseDatePicker from "@/components/ChineseDatePicker";
import KlineChart, { type KlineMarker } from "@/components/KlineChart";
import StockKeyboardWizard from "@/components/StockKeyboardWizard";

const { Title, Text } = Typography;

const WINDOW_OPTIONS = [
  { label: "120 日", value: 120 },
  { label: "250 日", value: 250 },
  { label: "500 日", value: 500 },
];

export default function GannAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialCode = searchParams.get("code") ?? "";

  const [code, setCode] = useState(initialCode);
  const [lastN, setLastN] = useState(250);
  const [queryToken, setQueryToken] = useState(initialCode ? Date.now() : 0);
  const [gannToken, setGannToken] = useState(0);
  const [upAnchorDraft, setUpAnchorDraft] = useState<Dayjs | null>(null);
  const [downAnchorDraft, setDownAnchorDraft] = useState<Dayjs | null>(null);
  const [appliedUpAnchor, setAppliedUpAnchor] = useState<string | undefined>();
  const [appliedDownAnchor, setAppliedDownAnchor] = useState<string | undefined>();

  const codeUpper = code.trim().toUpperCase();
  const enabled = queryToken > 0 && codeUpper.length > 0;

  const klineQ = useQuery({
    queryKey: ["gann-kline", codeUpper, lastN, queryToken],
    queryFn: () => getKline(codeUpper, { lastN }),
    enabled,
    retry: false,
  });

  const gannQ = useQuery({
    queryKey: [
      "gann",
      codeUpper,
      lastN,
      queryToken,
      gannToken,
      appliedUpAnchor,
      appliedDownAnchor,
    ],
    queryFn: () =>
      getGannAnalysis(codeUpper, {
        lastN,
        upAnchorDate: appliedUpAnchor,
        downAnchorDate: appliedDownAnchor,
      }),
    enabled,
    retry: false,
  });

  const klineDateRange = useMemo(() => {
    const candles = klineQ.data?.candles ?? [];
    if (!candles.length) return null;
    return {
      min: dayjs(candles[0].time.slice(0, 10)),
      max: dayjs(candles[candles.length - 1].time.slice(0, 10)),
    };
  }, [klineQ.data?.candles]);

  const disableOutOfWindow = useCallback(
    (d: Dayjs) => {
      if (!klineDateRange) return false;
      return (
        d.isBefore(klineDateRange.min, "day") || d.isAfter(klineDateRange.max, "day")
      );
    },
    [klineDateRange]
  );

  const hasDownLines = useMemo(
    () => (gannQ.data?.lines ?? []).some((l) => l.direction === "down"),
    [gannQ.data?.lines]
  );

  const markers = useMemo<KlineMarker[]>(() => {
    const out: KlineMarker[] = [];
    const { anchors, calibration } = gannQ.data ?? {};
    if (anchors?.up) {
      out.push({
        time: anchors.up.date,
        position: "belowBar",
        color: "#e91e63",
        shape: "circle",
        text: "上升起点",
      });
    }
    if (calibration?.up_ref) {
      out.push({
        time: calibration.up_ref.date,
        position: "aboveBar",
        color: "#d500f9",
        shape: "arrowUp",
        text: "第一波高点",
      });
    }
    if (hasDownLines && anchors?.down) {
      out.push({
        time: anchors.down.date,
        position: "aboveBar",
        color: "#5c6bc0",
        shape: "circle",
        text: "下降起点",
      });
    }
    if (hasDownLines && calibration?.down_ref) {
      out.push({
        time: calibration.down_ref.date,
        position: "belowBar",
        color: "#0288d1",
        shape: "arrowDown",
        text: "第一波低点",
      });
    }
    return out.sort((a, b) => a.time.localeCompare(b.time));
  }, [gannQ.data, hasDownLines]);

  const onSubmit = () => {
    if (!code.trim()) return;
    setSearchParams({ code: codeUpper });
    setUpAnchorDraft(null);
    setDownAnchorDraft(null);
    setAppliedUpAnchor(undefined);
    setAppliedDownAnchor(undefined);
    setGannToken(0);
    setQueryToken(Date.now());
  };

  const redrawGann = () => {
    setAppliedUpAnchor(upAnchorDraft?.format("YYYY-MM-DD"));
    setAppliedDownAnchor(downAnchorDraft?.format("YYYY-MM-DD"));
    setGannToken(Date.now());
  };

  const resetAnchors = () => {
    setUpAnchorDraft(null);
    setDownAnchorDraft(null);
    setAppliedUpAnchor(undefined);
    setAppliedDownAnchor(undefined);
    setGannToken(Date.now());
  };

  const applyStockCode = useCallback(
    (nextCode: string) => {
      setCode(nextCode);
      setSearchParams({ code: nextCode });
      setUpAnchorDraft(null);
      setDownAnchorDraft(null);
      setAppliedUpAnchor(undefined);
      setAppliedDownAnchor(undefined);
      setGannToken(0);
      setQueryToken(Date.now());
    },
    [setSearchParams]
  );

  const loading = klineQ.isLoading || gannQ.isLoading;
  const error = klineQ.error ?? gannQ.error;

  return (
    <>
      <StockKeyboardWizard onSelect={(c) => applyStockCode(c)} />
      <div className="page-heading">
        <div>
          <Title level={2}>江恩角度线</Title>
          <Typography.Paragraph type="secondary">以起涨低点与波段高点校准趋势扇形，支持手动调整锚点</Typography.Paragraph>
        </div>
      </div>

      <Card className="workbench-form-card" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]} align="bottom">
          <Col className="workbench-field">
            <label>股票代码</label>
            <Input
              value={code}
              placeholder="如 SZ002281"
              onChange={(e) => setCode(e.target.value)}
              onPressEnter={onSubmit}
              style={{ width: 220 }}
            />
          </Col>
          <Col className="workbench-field">
            <label>分析窗口</label>
            <Select
              value={lastN}
              onChange={setLastN}
              options={WINDOW_OPTIONS}
              style={{ width: 120 }}
            />
          </Col>
          <Col className="workbench-form-actions" style={{ marginLeft: "auto" }}>
            <Button type="primary" icon={<SearchOutlined />} onClick={onSubmit}>
              分析
            </Button>
          </Col>
        </Row>
        <div className="workbench-form-section">
          <div className="workbench-form-section-head"><strong>锚点设置</strong><span>留空时由系统自动识别</span></div>
        <Row gutter={[16, 12]} align="bottom">
          <Col className="workbench-field">
            <label>上升起点</label>
            <ChineseDatePicker
              value={upAnchorDraft}
              onChange={setUpAnchorDraft}
              placeholder="自动识别"
              allowClear
              minDate={klineDateRange?.min}
              maxDate={klineDateRange?.max}
              disabledDate={disableOutOfWindow}
              style={{ width: 160 }}
            />
          </Col>
          <Col className="workbench-field">
            <label>下降起点</label>
            <ChineseDatePicker
              value={downAnchorDraft}
              onChange={setDownAnchorDraft}
              placeholder="自动（窗口最高）"
              allowClear
              minDate={klineDateRange?.min}
              maxDate={klineDateRange?.max}
              disabledDate={disableOutOfWindow}
              style={{ width: 160 }}
            />
          </Col>
          <Col className="workbench-form-actions" style={{ marginLeft: "auto" }}>
            <Button icon={<RedoOutlined />} onClick={redrawGann} disabled={!enabled}>
              重绘江恩线
            </Button>
            <Button onClick={resetAnchors} disabled={!enabled || (!appliedUpAnchor && !appliedDownAnchor && !upAnchorDraft && !downAnchorDraft)}>
              恢复自动
            </Button>
          </Col>
        </Row>
        </div>
        {(appliedUpAnchor || appliedDownAnchor) && (
          <Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
            当前手动起点：
            {appliedUpAnchor ? ` 上升 ${appliedUpAnchor}` : ""}
            {appliedDownAnchor ? ` 下降 ${appliedDownAnchor}` : ""}
          </Text>
        )}
      </Card>

      {loading && (
        <Card>
          <Spin spinning tip="正在计算江恩角度线…">
            <div style={{ minHeight: 120 }} />
          </Spin>
        </Card>
      )}

      {error && (
        <Alert
          type="error"
          message="分析失败"
          description={(error as Error).message}
          showIcon
        />
      )}

      {gannQ.data && klineQ.data && !loading && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          {gannQ.data.note && (
            <Alert type="warning" message={gannQ.data.note} showIcon />
          )}

          <Card size="small">
            <Row gutter={16}>
              <Col span={8}>
                <Text type="secondary">股票</Text>
                <div>
                  <Text strong style={{ fontSize: 18 }}>
                    {gannQ.data.code}
                  </Text>
                  {gannQ.data.name && (
                    <Text type="secondary" style={{ marginLeft: 8 }}>
                      {gannQ.data.name}
                    </Text>
                  )}
                </div>
              </Col>
              <Col span={8}>
                <Text type="secondary">1×1 斜率（形态校准）</Text>
                <div>
                  <Text strong>{gannQ.data.price_scale.toFixed(4)}</Text>
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    元/日
                  </Text>
                </div>
              </Col>
              <Col span={8}>
                <Text type="secondary">分析窗口</Text>
                <div>
                  <Text strong>{gannQ.data.window_bars}</Text>
                  <Text type="secondary" style={{ marginLeft: 4 }}>
                    根 K 线
                  </Text>
                </div>
              </Col>
            </Row>
          </Card>

          <Card title="关键拐点" size="small">
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="上升起点">
                {gannQ.data.anchors.up ? (
                  <>
                    {gannQ.data.anchors.up.date} · 低 {gannQ.data.anchors.up.price}
                    <Tag color="magenta" style={{ marginLeft: 8 }}>
                      {gannQ.data.anchors.up.reason}
                    </Tag>
                  </>
                ) : (
                  "—"
                )}
              </Descriptions.Item>
              <Descriptions.Item label="第一波高点（8×1 校准）">
                {gannQ.data.calibration.up_ref ? (
                  <>
                    {gannQ.data.calibration.up_ref.date} · 高{" "}
                    {gannQ.data.calibration.up_ref.price}
                    <Tag color="purple" style={{ marginLeft: 8 }}>
                      {gannQ.data.calibration.up_ref.reason}
                    </Tag>
                  </>
                ) : (
                  "—"
                )}
              </Descriptions.Item>
              <Descriptions.Item label="下降起点（窗口最高）">
                {gannQ.data.anchors.down ? (
                  <>
                    {gannQ.data.anchors.down.date} · 高 {gannQ.data.anchors.down.price}
                    <Tag color="geekblue" style={{ marginLeft: 8 }}>
                      {gannQ.data.anchors.down.reason}
                    </Tag>
                  </>
                ) : (
                  "—"
                )}
              </Descriptions.Item>
              <Descriptions.Item label="第一波低点（8×1 校准）">
                {gannQ.data.calibration.down_ref ? (
                  <>
                    {gannQ.data.calibration.down_ref.date} · 低{" "}
                    {gannQ.data.calibration.down_ref.price}
                    <Tag color="geekblue" style={{ marginLeft: 8 }}>
                      {gannQ.data.calibration.down_ref.reason}
                    </Tag>
                  </>
                ) : (
                  "—"
                )}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title="K 线 + 江恩角度线" size="small">
            <KlineChart
              data={klineQ.data}
              markers={markers}
              gannLines={gannQ.data.lines}
              height={620}
              focusDate={gannQ.data.anchors.up?.date}
              visibleBars={Math.min(lastN, 120)}
            />
          </Card>
        </Space>
      )}
    </>
  );
}
