import { useMemo, useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  InputNumber,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";

import { fetchStrategies } from "@/api/strategies";
import { runScan, type ScanRow } from "@/api/scan";
import ParamForm from "@/components/ParamForm";
import {
  loadScanPageCache,
  saveScanPageCache,
  SCAN_PAGE_QUERY_KEY,
  type ScanPageCache,
} from "@/utils/scanCache";

const { Title, Text } = Typography;

const TIER_COLOR: Record<string, string> = {
  A: "magenta",
  B: "red",
  C: "orange",
  D: "default",
};

export default function ScanPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  const initialCache = useMemo(() => {
    const fromQuery = queryClient.getQueryData<ScanPageCache>(SCAN_PAGE_QUERY_KEY);
    if (fromQuery) return fromQuery;
    const fromSession = loadScanPageCache();
    if (fromSession) {
      queryClient.setQueryData(SCAN_PAGE_QUERY_KEY, fromSession);
    }
    return fromSession;
  }, [queryClient]);

  const [strategyName, setStrategyName] = useState<string>(
    initialCache?.strategyName ?? "breakout_washout"
  );
  const [params, setParams] = useState<Record<string, unknown>>(initialCache?.params ?? {});
  const [targetDate, setTargetDate] = useState<Dayjs | null>(
    initialCache?.targetDate ? dayjs(initialCache.targetDate) : null
  );
  const [limit, setLimit] = useState<number>(initialCache?.limit ?? 200);
  const [maxCodes, setMaxCodes] = useState<number | null>(initialCache?.maxCodes ?? null);
  const [debugMode, setDebugMode] = useState<boolean>(initialCache?.debugMode ?? false);
  const [scanResult, setScanResult] = useState<ScanPageCache["result"] | null>(
    initialCache?.result ?? null
  );

  const persistScanCache = (result: ScanPageCache["result"]) => {
    const cache: ScanPageCache = {
      strategyName,
      params,
      targetDate: targetDate ? targetDate.format("YYYY-MM-DD") : null,
      limit,
      maxCodes,
      debugMode,
      result,
    };
    queryClient.setQueryData(SCAN_PAGE_QUERY_KEY, cache);
    saveScanPageCache(cache);
    setScanResult(result);
  };

  const { data: strategyPack } = useQuery({
    queryKey: ["strategies"],
    queryFn: fetchStrategies,
    staleTime: 30_000,
  });
  const strategies = strategyPack?.strategies;

  useEffect(() => {
    if (initialCache?.strategyName || !strategyPack) return;
    setStrategyName(strategyPack.default_strategy);
  }, [initialCache?.strategyName, strategyPack]);

  const currentStrategy = useMemo(
    () => strategies?.find((s) => s.name === strategyName),
    [strategies, strategyName]
  );

  const scanMutation = useMutation({
    mutationFn: () =>
      runScan({
        strategy: strategyName,
        params,
        target_date: targetDate ? targetDate.format("YYYY-MM-DD") : null,
        limit,
        sort_by: "score",
        desc: true,
        max_codes: debugMode ? maxCodes : null,
      }),
    onSuccess: (r) => {
      persistScanCache(r);
      if (r.warning) {
        message.warning(r.warning);
      } else {
        message.success(`命中 ${r.total} 条，扫描 ${r.scanned} 只股票，耗时 ${r.took_ms}ms`);
      }
    },
    onError: (e: Error) => message.error("扫描失败：" + e.message),
  });

  const columns: ColumnsType<ScanRow> = [
    {
      title: "代码",
      dataIndex: "code",
      width: 105,
      fixed: "left",
      render: (v: string) => (
        <a onClick={() => navigate(`/diagnose?code=${v}&date=${scanResult?.target_date ?? ""}&strategy=${strategyName}`)}>
          {v}
        </a>
      ),
    },
    {
      title: "名称",
      dataIndex: "name",
      width: 120,
      fixed: "left",
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    { title: "板块", dataIndex: "market", width: 80 },
    {
      title: "等级",
      dataIndex: "tier",
      width: 70,
      align: "center",
      render: (t: string) => <Tag color={TIER_COLOR[t]}>{t}</Tag>,
      sorter: (a, b) => a.tier.localeCompare(b.tier),
    },
    {
      title: "评分",
      dataIndex: "score",
      width: 90,
      align: "right",
      sorter: (a, b) => a.score - b.score,
      defaultSortOrder: "descend",
      render: (v: number) => <Text strong>{v.toFixed(2)}</Text>,
    },
    {
      title: "突破%",
      dataIndex: "breakout_pct",
      width: 80,
      align: "right",
      sorter: (a, b) => a.breakout_pct - b.breakout_pct,
      render: (v: number) => (
        <Text style={{ color: v > 5 ? "#cf1322" : undefined }}>{v.toFixed(2)}</Text>
      ),
    },
    {
      title: "涨停",
      dataIndex: "is_limit_up",
      width: 60,
      align: "center",
      render: (v: boolean) => (v ? <Tag color="red">涨停</Tag> : null),
    },
    {
      title: "收盘",
      dataIndex: "close",
      width: 80,
      align: "right",
    },
    {
      title: "试盘日",
      dataIndex: "test_date",
      width: 110,
    },
    {
      title: "距试盘",
      dataIndex: "days_since_test",
      width: 80,
      align: "right",
      render: (v: number) => `${v}d`,
    },
    {
      title: "回踩%",
      dataIndex: "pullback_pct",
      width: 80,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "量比",
      dataIndex: "vol_ratio",
      width: 70,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "MACD",
      dataIndex: "macd",
      width: 90,
      align: "right",
      render: (v: number) => v.toFixed(3),
    },
    {
      title: "MA粘合%",
      dataIndex: "ma_spread_pct",
      width: 90,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "close/MA30",
      dataIndex: "close_to_ma30",
      width: 100,
      align: "right",
    },
    {
      title: "当日涨%",
      dataIndex: "day_change_pct",
      width: 90,
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
  ];

  return (
    <>
      <Title level={3} style={{ marginTop: 0 }}>
        选股扫描
      </Title>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 16 }}>
          <Col>
            <Text>策略：</Text>
            <Select
              value={strategyName}
              onChange={(v) => {
                setStrategyName(v);
                setParams({});
              }}
              options={(strategies ?? []).map((s) => ({ label: s.label, value: s.name }))}
              style={{ width: 200, marginLeft: 8 }}
            />
          </Col>
          <Col>
            <Text>交易日：</Text>
            <DatePicker
              value={targetDate}
              onChange={setTargetDate}
              placeholder="留空=最后一日"
              format="YYYY-MM-DD"
              style={{ marginLeft: 8 }}
            />
          </Col>
          <Col>
            <Text>取前 N：</Text>
            <InputNumber
              value={limit}
              onChange={(v) => setLimit(v ?? 200)}
              min={1}
              max={5000}
              style={{ width: 100, marginLeft: 8 }}
            />
          </Col>
          <Col>
            <Switch
              checked={debugMode}
              onChange={setDebugMode}
              checkedChildren="调试"
              unCheckedChildren="全市场"
            />
          </Col>
          {debugMode && (
            <Col>
              <Text>只扫前 N 只：</Text>
              <InputNumber
                value={maxCodes ?? undefined}
                onChange={(v) => setMaxCodes(v ?? null)}
                min={1}
                max={5000}
                placeholder="如 100"
                style={{ width: 120, marginLeft: 8 }}
              />
            </Col>
          )}
          <Col flex="auto" style={{ textAlign: "right" }}>
            <Space>
              <Button
                type="primary"
                icon={<SearchOutlined />}
                loading={scanMutation.isPending}
                onClick={() => scanMutation.mutate()}
              >
                开始扫描
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => {
                  setParams({});
                  message.info("已重置参数为默认值");
                }}
              >
                重置参数
              </Button>
            </Space>
          </Col>
        </Row>

        {currentStrategy && (
          <ParamForm
            schema={currentStrategy.params_schema}
            value={params}
            onChange={setParams}
          />
        )}
      </Card>

      {scanResult ? (
        <Card
          title={
            <Space>
              <Statistic
                title="命中"
                value={scanResult.total}
                valueStyle={{ fontSize: 18, color: "#cf1322" }}
              />
              <Statistic
                title="扫描"
                value={scanResult.scanned}
                valueStyle={{ fontSize: 18 }}
              />
              <Statistic
                title="耗时"
                value={`${scanResult.took_ms} ms`}
                valueStyle={{ fontSize: 18 }}
              />
            </Space>
          }
        >
          <Table<ScanRow>
            rowKey="code"
            dataSource={scanResult.rows}
            columns={columns}
            size="small"
            scroll={{ x: 1600 }}
            pagination={{ pageSize: 30, showSizeChanger: true }}
          />
        </Card>
      ) : (
        <Empty description="点击「开始扫描」运行" />
      )}
    </>
  );
}
