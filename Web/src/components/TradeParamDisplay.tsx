import { Descriptions } from "antd";

import {
  formatTradeParamValue,
  TRADE_PARAM_LABELS,
} from "@/lib/backtestRuntime";

interface Props {
  params: Record<string, unknown>;
  title?: string;
}

export default function TradeParamDisplay({ params, title }: Props) {
  const keys = Object.keys(TRADE_PARAM_LABELS).filter((k) => k in params);
  if (keys.length === 0) return null;

  return (
    <Descriptions
      size="small"
      bordered
      column={3}
      title={title}
      style={{ marginTop: title ? 8 : 0 }}
    >
      {keys.map((k) => (
        <Descriptions.Item key={k} label={TRADE_PARAM_LABELS[k] ?? k}>
          {formatTradeParamValue(k, params[k])}
        </Descriptions.Item>
      ))}
    </Descriptions>
  );
}
