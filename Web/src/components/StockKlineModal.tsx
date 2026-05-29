import { useMemo } from "react";

import { useQuery } from "@tanstack/react-query";

import { Alert, Modal, Space, Spin, Tag, Typography } from "antd";



import { getKline } from "@/api/diagnose";

import KlineChart, { type KlineMarker } from "@/components/KlineChart";



const { Text } = Typography;



/** 回测 K 线：以信号日为中心的数据窗口与视口宽度 */

const KLINE_LAST_N = 160;

const KLINE_VISIBLE_BARS = 100;

const KLINE_CHART_HEIGHT = 640;



export interface StockKlineTarget {

  code: string;

  name?: string;

  signalDate?: string;

  buyDate?: string;

  sellDate?: string;

}



interface Props {

  open: boolean;

  stock: StockKlineTarget | null;

  onClose: () => void;

}



function latestDate(...dates: (string | undefined)[]): string | undefined {

  const valid = dates.filter(Boolean) as string[];

  if (!valid.length) return undefined;

  return valid.sort().at(-1);

}



function earliestDate(...dates: (string | undefined)[]): string | undefined {

  const valid = dates.filter(Boolean) as string[];

  if (!valid.length) return undefined;

  return valid.sort()[0];

}



/** 同时标记信号 / 买入 / 卖出（同一天可并存多条标记）。 */

function buildMarkers(stock: StockKlineTarget): KlineMarker[] {

  const out: KlineMarker[] = [];



  if (stock.signalDate && stock.signalDate !== stock.buyDate) {

    out.push({

      time: stock.signalDate,

      position: "aboveBar",

      color: "#1677ff",

      shape: "circle",

      text: "信号",

    });

  }



  if (stock.buyDate) {

    out.push({

      time: stock.buyDate,

      position: "belowBar",

      color: "#cf1322",

      shape: "arrowUp",

      text: stock.signalDate === stock.buyDate ? "信号/买入" : "买入",

    });

  }



  if (stock.sellDate) {

    out.push({

      time: stock.sellDate,

      position: "aboveBar",

      color: "#3f8600",

      shape: "arrowDown",

      text: "卖出",

    });

  }



  return out.sort((a, b) => a.time.localeCompare(b.time));

}



export default function StockKlineModal({ open, stock, onClose }: Props) {

  const centerDate = stock?.signalDate ?? stock?.buyDate;

  const minDate = stock

    ? earliestDate(stock.signalDate, stock.buyDate, stock.sellDate)

    : undefined;

  const maxDate = stock ? latestDate(stock.buyDate, stock.sellDate) : undefined;



  const klineQ = useQuery({

    queryKey: ["stock-kline", stock?.code, centerDate, minDate, maxDate],

    queryFn: () =>

      getKline(stock!.code, {

        lastN: KLINE_LAST_N,

        centerDate,

        minDate,

        maxDate,

      }),

    enabled: open && !!stock?.code && !!centerDate,

    retry: false,

  });



  const markers = useMemo(() => (stock ? buildMarkers(stock) : []), [stock]);



  const title = stock ? (

    <Space wrap size={8}>

      <Text strong>{stock.code}</Text>

      {stock.name && <Text>{stock.name}</Text>}

      {stock.buyDate && <Tag color="red">买 {stock.buyDate}</Tag>}

      {stock.sellDate && <Tag color="green">卖 {stock.sellDate}</Tag>}

      {stock.signalDate && stock.signalDate !== stock.buyDate && (

        <Tag color="blue">信号 {stock.signalDate}</Tag>

      )}

    </Space>

  ) : (

    "K 线"

  );



  return (

    <Modal

      open={open}

      onCancel={onClose}

      footer={null}

      width="min(1400px, 98vw)"

      centered
      destroyOnHidden
      styles={{ body: { paddingTop: 8, paddingBottom: 12 } }}

      title={title}

    >

      {klineQ.isLoading && (

        <Spin spinning>

          <div style={{ minHeight: KLINE_CHART_HEIGHT }} />

        </Spin>

      )}

      {klineQ.error && (

        <Alert

          type="error"

          showIcon

          message="K 线加载失败"

          description={(klineQ.error as Error).message}

        />

      )}

      {klineQ.data && centerDate && (

        <KlineChart

          data={klineQ.data}

          markers={markers}

          height={KLINE_CHART_HEIGHT}

          focusDate={centerDate}

          visibleBars={KLINE_VISIBLE_BARS}

        />

      )}

    </Modal>

  );

}


