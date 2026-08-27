import { useMemo } from "react";
import { Col, Collapse, Row, Tooltip, Typography } from "@/components/ui";

import type { StrategyParamSchema } from "@/api/scan";
import { getParamDesc, getParamLabel, getTypeLabel } from "@/utils/paramLabels";

const { Text } = Typography;

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

function formatParamValue(value: unknown, type?: string): string {
  if (value === null || value === undefined) return "—";
  if (type === "bool" || typeof value === "boolean") return value ? "开" : "关";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return String(value);
    const s = value.toFixed(6).replace(/\.?0+$/, "");
    return s || "0";
  }
  return String(value);
}

interface Props {
  schema?: Record<string, StrategyParamSchema>;
  params: Record<string, unknown>;
  compact?: boolean;
}

export default function ParamDisplay({ schema, params, compact = false }: Props) {
  const entries = useMemo(() => {
    const keys = schema ? Object.keys(schema) : Object.keys(params);
    return keys
      .filter((k) => k in params)
      .map((k) => [k, schema?.[k], params[k]] as const);
  }, [schema, params]);

  const { coreFields, advancedFields } = useMemo(() => {
    const core: (typeof entries)[number][] = [];
    const adv: (typeof entries)[number][] = [];
    entries.forEach((e) => {
      if (CORE_FIELDS.has(e[0])) core.push(e);
      else adv.push(e);
    });
    return { coreFields: core, advancedFields: adv };
  }, [entries]);

  if (!entries.length) {
    return <Text type="secondary">无策略参数</Text>;
  }

  const renderField = (key: string, sch: StrategyParamSchema | undefined, value: unknown) => {
    const label = getParamLabel(key);
    const desc = getParamDesc(key);
    const tooltip = (
      <div style={{ fontSize: 12, lineHeight: 1.6 }}>
        <div>
          <Text code style={{ fontSize: 12, color: "#fff" }}>
            {key}
          </Text>
          {sch && (
            <Text style={{ color: "rgba(255,255,255,0.65)" }}> · {getTypeLabel(sch.type)}</Text>
          )}
        </div>
        {sch && (
          <div style={{ color: "rgba(255,255,255,0.85)" }}>默认值：{String(sch.default)}</div>
        )}
        {desc && <div style={{ color: "rgba(255,255,255,0.85)" }}>{desc}</div>}
      </div>
    );
    return (
      <Col key={key} xs={24} sm={12} md={compact ? 12 : 8} xl={compact ? 8 : 6}>
        <div style={{ marginBottom: 4 }}>
          <Tooltip title={tooltip} placement="topLeft" mouseEnterDelay={0.3}>
            <Text
              type="secondary"
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
        <Text>{formatParamValue(value, sch?.type)}</Text>
      </Col>
    );
  };

  const renderGroup = (fields: (typeof entries)[number][]) => (
    <Row gutter={[16, 12]}>
      {fields.map(([k, s, v]) => renderField(k, s, v))}
    </Row>
  );

  if (compact) {
    return renderGroup(entries);
  }

  return (
    <div>
      {coreFields.length > 0 && <div style={{ marginBottom: 12 }}>{renderGroup(coreFields)}</div>}
      {advancedFields.length > 0 && (
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
      )}
    </div>
  );
}
