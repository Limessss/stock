import { Col, InputNumber, Row, Select, Space, Switch, Tooltip, Typography } from "@/components/ui";

import ChineseDatePicker from "@/components/ChineseDatePicker";
import type { BacktestRuntimeState } from "@/lib/backtestRuntime";

const { Text } = Typography;

interface Props {
  value: BacktestRuntimeState;
  onChange: (v: BacktestRuntimeState) => void;
  showDates?: boolean;
}

export default function BacktestRuntimeFields({ value, onChange, showDates = true }: Props) {
  const set = (patch: Partial<BacktestRuntimeState>) => onChange({ ...value, ...patch });

  return (
    <Row gutter={[16, 16]}>
      {showDates && (
        <>
          <Col xs={24} sm={12} md={6} className="runtime-field">
            <Text type="secondary">起始日</Text>
            <ChineseDatePicker
              value={value.startDate}
              onChange={(d) => d && set({ startDate: d })}
              style={{ width: "100%" }}
            />
          </Col>
          <Col xs={24} sm={12} md={6} className="runtime-field">
            <Text type="secondary">结束日</Text>
            <ChineseDatePicker
              value={value.endDate}
              onChange={(d) => d && set({ endDate: d })}
              style={{ width: "100%" }}
            />
          </Col>
        </>
      )}
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Text type="secondary">止盈</Text>
        <InputNumber
          value={value.takeProfit}
          onChange={(v) => set({ takeProfit: v ?? 0.2 })}
          step={0.01}
          min={0.01}
          max={2.0}
          style={{ width: "100%" }}
          formatter={(v) => `+${((v as number) * 100).toFixed(0)}%`}
          parser={(v) => Number((v ?? "0").replace(/[^0-9.]/g, "")) / 100}
        />
      </Col>
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Text type="secondary">止损</Text>
        <InputNumber
          value={value.stopLoss}
          onChange={(v) => set({ stopLoss: v ?? 0.07 })}
          step={0.01}
          min={0.01}
          max={0.5}
          style={{ width: "100%" }}
          formatter={(v) => `-${((v as number) * 100).toFixed(0)}%`}
          parser={(v) => Number((v ?? "0").replace(/[^0-9.]/g, "")) / 100}
        />
      </Col>
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Text type="secondary">最长持有</Text>
        <Space.Compact style={{ width: "100%" }}>
          <InputNumber
            value={value.maxHold}
            onChange={(v) => set({ maxHold: v ?? 20 })}
            min={1}
            max={120}
            style={{ width: "100%" }}
          />
          <span className="input-unit">
            日
          </span>
        </Space.Compact>
      </Col>
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Text type="secondary">分批止盈</Text>
        <InputNumber
          value={value.splitTp ?? undefined}
          onChange={(v) => set({ splitTp: v ?? null })}
          step={0.01}
          min={0}
          max={1}
          placeholder="留空=不分批"
          style={{ width: "100%" }}
        />
      </Col>
      <Col xs={24} sm={12} md={6} className="runtime-field">
        <Text type="secondary">初始资金</Text>
        <Space.Compact style={{ width: "100%" }}>
          <InputNumber
            value={value.initialCapital}
            onChange={(v) => set({ initialCapital: v ?? 1_000_000 })}
            min={10_000}
            max={100_000_000}
            step={100_000}
            style={{ width: "100%" }}
            formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}
            parser={(v) => Number((v ?? "0").replace(/,/g, ""))}
          />
          <span className="input-unit">
            元
          </span>
        </Space.Compact>
      </Col>
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Tooltip title="单笔最多使用 min(当前可用现金, 初始资金×比例)">
          <Text type="secondary">单笔仓位</Text>
        </Tooltip>
        <InputNumber
          value={value.positionPct}
          onChange={(v) => set({ positionPct: v ?? 1 })}
          min={0.01}
          max={1}
          step={0.05}
          style={{ width: "100%" }}
          formatter={(v) => `${((v as number) * 100).toFixed(0)}%`}
          parser={(v) => Number((v ?? "0").replace(/[^0-9.]/g, "")) / 100}
        />
      </Col>
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Tooltip title="1=串行全仓；>1 允许多股同时持仓">
          <Text type="secondary">最大持仓</Text>
        </Tooltip>
        <Space.Compact style={{ width: "100%" }}>
          <InputNumber
            value={value.maxConcurrent}
            onChange={(v) => set({ maxConcurrent: v ?? 1 })}
            min={1}
            max={20}
            style={{ width: "100%" }}
          />
          <span className="input-unit">
            只
          </span>
        </Space.Compact>
      </Col>
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Text type="secondary">交易制度</Text>
        <Tooltip title="A 股 T+1：买入当日不可卖出">
          <div className="workbench-switch-field">
            <Switch
              checked={value.tPlus1}
              onChange={(c) => set({ tPlus1: c })}
              checkedChildren="T+1 开启"
              unCheckedChildren="T+1 关闭"
            />
          </div>
        </Tooltip>
      </Col>
      <Col xs={12} sm={8} md={4} className="runtime-field">
        <Text type="secondary">回测范围</Text>
        <div className="workbench-switch-field"><Switch checked={value.debugMode} onChange={(c) => set({ debugMode: c })} checkedChildren="调试样本" unCheckedChildren="全市场" /></div>
      </Col>
      {value.debugMode && <Col xs={12} sm={8} md={4} className="runtime-field">
        <Text type="secondary">样本数量</Text>
        <InputNumber value={value.maxCodes ?? undefined} onChange={(v) => set({ maxCodes: v ?? null })} min={10} max={6000} placeholder="只扫前 N 只" />
      </Col>}
      <Col xs={12} sm={8} md={4} className="runtime-field">
          <Tooltip title="默认 8。Windows 多进程需在无 reload 模式下启动后端。">
            <Text type="secondary">并行度</Text>
          </Tooltip>
          <InputNumber
            value={value.numWorkers ?? undefined}
            onChange={(v) => set({ numWorkers: v ?? null })}
            min={1}
            max={32}
            placeholder="8"
            style={{ width: "100%" }}
          />
      </Col>
      <Col xs={24} sm={12} md={6} className="runtime-field">
          <Text type="secondary">回测引擎</Text>
          <Select
            value={value.engine}
            onChange={(v) => set({ engine: v })}
            options={[
              { label: "legacy（精确）", value: "legacy" },
              { label: "vectorbt（实验）", value: "vectorbt" },
            ]}
            style={{ width: "100%" }}
          />
      </Col>
    </Row>
  );
}
