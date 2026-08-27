import { useEffect, useMemo, useState } from "react";
import { Col, Collapse, InputNumber, Row, Switch, Tooltip, Typography } from "@/components/ui";

import type { StrategyParamSchema } from "@/api/scan";
import { getParamDesc, getParamLabel, getTypeLabel } from "@/utils/paramLabels";

const { Text } = Typography;

// 把参数分到「核心」和「高级」两组，按经验值挑选
const CORE_FIELDS = new Set([
  "winrate_mode",
  "min_breakout_pct",
  "min_break_pct",
  "breakout_vol_ratio",
  "min_today_vol_ratio",
  "min_ma_bull_count",
  "max_close_ma30_ratio",
  "max_close_over_washout",
  "max_break_pct",
  "min_pullback_pct",
  "max_pullback_pct",
  "min_day_change",
  "require_positive_macd_hist",
  "enable_strong_breakout",
  "min_probe_gain",
]);

interface Props {
  schema: Record<string, StrategyParamSchema>;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}

export default function ParamForm({ schema, value, onChange }: Props) {
  const [local, setLocal] = useState<Record<string, unknown>>(value);

  // schema 变化时填充默认值
  useEffect(() => {
    const defaults: Record<string, unknown> = {};
    Object.entries(schema).forEach(([k, v]) => {
      defaults[k] = v.default;
    });
    const filteredValue: Record<string, unknown> = {};
    Object.keys(schema).forEach((k) => {
      if (k in value) filteredValue[k] = value[k];
    });
    const merged = { ...defaults, ...filteredValue };
    setLocal(merged);
    onChange(merged);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema]);

  const update = (k: string, v: unknown) => {
    const next = { ...local, [k]: v };
    setLocal(next);
    onChange(next);
  };

  const renderField = (key: string, sch: StrategyParamSchema) => {
    const v = local[key];
    if (sch.type === "bool") {
      return (
        <Switch
          checked={!!v}
          onChange={(c) => update(key, c)}
          checkedChildren="开"
          unCheckedChildren="关"
        />
      );
    }
    // int / float / 其他都用 InputNumber
    const isInt = sch.type === "int";
    return (
      <InputNumber
        value={v as number}
        onChange={(n) => update(key, n)}
        step={isInt ? 1 : 0.01}
        style={{ width: "100%" }}
      />
    );
  };

  const { coreFields, advancedFields } = useMemo(() => {
    const core: [string, StrategyParamSchema][] = [];
    const adv: [string, StrategyParamSchema][] = [];
    Object.entries(schema).forEach(([k, v]) => {
      if (CORE_FIELDS.has(k)) core.push([k, v]);
      else adv.push([k, v]);
    });
    return { coreFields: core, advancedFields: adv };
  }, [schema]);

  const renderGroup = (fields: [string, StrategyParamSchema][]) => (
    <Row gutter={[16, 14]} className="parameter-grid">
      {fields.map(([k, s]) => {
        const label = getParamLabel(k);
        const desc = getParamDesc(k);
        const tooltip = (
          <div style={{ fontSize: 12, lineHeight: 1.6 }}>
            <div>
              <Text code style={{ fontSize: 12, color: "#fff" }}>{k}</Text>{" "}
              <Text style={{ color: "rgba(255,255,255,0.65)" }}>· {getTypeLabel(s.type)}</Text>
            </div>
            <div style={{ color: "rgba(255,255,255,0.85)" }}>
              默认值：{String(s.default)}
            </div>
            {desc && <div style={{ color: "rgba(255,255,255,0.85)" }}>{desc}</div>}
          </div>
        );
        return (
          <Col key={k} xs={24} sm={12} md={8} xl={6}>
            <div style={{ marginBottom: 4 }}>
              <Tooltip title={tooltip} placement="topLeft" mouseEnterDelay={0.3}>
                <Text
                  style={{
                    fontSize: 12,
                    cursor: "help",
                    borderBottom: "1px dotted rgba(0,0,0,0.25)",
                  }}
                >
                  {label}
                </Text>
              </Tooltip>
            </div>
            {renderField(k, s)}
          </Col>
        );
      })}
    </Row>
  );

  return (
    <div>
      <div style={{ marginBottom: 12 }}>{renderGroup(coreFields)}</div>
      <Collapse
        size="small"
        items={[
          {
            key: "adv",
            label: `高级参数（${advancedFields.length} 项）`,
            children: renderGroup(advancedFields),
          },
        ]}
      />
    </div>
  );
}
