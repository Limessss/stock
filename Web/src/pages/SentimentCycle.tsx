import { type UIEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Empty,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "@/components/ui";
import {
  CloudDownloadOutlined,
  ReloadOutlined,
} from "@/components/ui/icons";
import dayjs from "dayjs";

import {
  fetchSentimentDay,
  fetchSentimentMatrix,
  syncSentimentLatest,
  updateMajorFirstBoards,
  type SentimentDay,
  type SentimentLadderItem,
  type SentimentNegativeFeedbackItem,
} from "@/api/sentiment";
import ChineseDatePicker from "@/components/ChineseDatePicker";
import StockKlineModal, { type StockKlineTarget } from "@/components/StockKlineModal";
import { BEIJING_TZ, nowBeijing, parseApiTime } from "@/lib/dayjsSetup";

const { Title, Text, Paragraph } = Typography;
const MATRIX_PAGE_SIZE = 30;
const MATRIX_COLUMN_WIDTH = 168;
const MATRIX_LABEL_WIDTH = 116;
const MATRIX_LOAD_THRESHOLD = MATRIX_COLUMN_WIDTH * 2;
const MATRIX_OVERSCAN_COLUMNS = 3;

const EXTERNAL_STATUS_LABEL: Record<string, string> = {
  not_configured: "未配置",
  pending: "待同步",
  partial: "部分完成",
  complete: "已完成",
  error: "异常",
};

function formatPct(value: number | null): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatAmount(value: number | null): string {
  if (value == null) return "—";
  if (value >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(2)}万亿`;
  return `${Math.round(value / 100_000_000).toLocaleString()}亿`;
}

function formatLimitTime(value: number | null): string {
  if (!value) return "";
  return dayjs.unix(value).tz(BEIJING_TZ).format("HH:mm:ss");
}

function sourceTag(source: string) {
  const color = source === "local" ? "blue" : source === "kaipanla" ? "purple" : source === "derived" ? "cyan" : "default";
  const label = source === "local" ? "本地" : source === "kaipanla" ? "开盘啦缓存" : source === "derived" ? "本地×开盘啦" : "人工";
  return <Tag color={color}>{label}</Tag>;
}

function ThemeList({ items }: { items: SentimentDay["limit_up_themes"] }) {
  if (!items.length) return <Text type="secondary">—</Text>;
  return (
    <Space wrap size={[4, 4]}>
      {items.map((item) => (
        <Tag key={item.id} color="geekblue">
          {item.name}{item.count != null ? ` ${item.count}` : ""}
        </Tag>
      ))}
    </Space>
  );
}

function SectorList({
  items,
  tone,
}: {
  items: SentimentDay["strong_sectors"];
  tone: "strong" | "weak";
}) {
  if (!items.length) return <Text type="secondary">—</Text>;
  return (
    <Space wrap size={[4, 4]}>
      {items.map((item) => (
        <Tag key={item.id} color={tone === "strong" ? "red" : "green"}>
          {item.rank}. {item.name} {item.count ?? "—"}
          {item.stage !== "" && Number.isFinite(Number(item.stage))
            ? ` / ${formatPct(Number(item.stage))}`
            : ""}
        </Tag>
      ))}
    </Space>
  );
}

function MatrixStockCards({
  stocks,
  tradeDate,
  onOpen,
  highlightKeys,
}: {
  stocks: SentimentLadderItem[];
  tradeDate: string;
  onOpen: (target: StockKlineTarget) => void;
  highlightKeys?: Set<string>;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!stocks.length) return <Text type="secondary">—</Text>;
  const visibleStocks = stocks.slice(0, 4);
  const hiddenCount = stocks.length - visibleStocks.length;
  const boardCount = stocks[0]?.continuous_board_count;

  const renderCard = (stock: SentimentLadderItem) => {
    const isCycleLeader = highlightKeys?.has(`${tradeDate}:${stock.code}`);
    const limitReason = stock.reason.trim() || "暂无涨停原因";
    return (
      <Tooltip
        key={stock.id}
        title={`涨停原因：${limitReason}${isCycleLeader ? "（本轮后续晋级6板+）" : ""}`}
      >
        <button
          type="button"
          className={`sentiment-matrix-stock-card ${(stock.continuous_board_count ?? 0) >= 5 ? "is-high" : ""} ${isCycleLeader ? "is-cycle-leader" : ""}`}
          onClick={() => onOpen({ code: stock.code, name: stock.name, signalDate: tradeDate })}
        >
          <div className="sentiment-matrix-stock-title">
            <strong>{stock.name || stock.code}</strong>
            {stock.board_type && <span className="sentiment-matrix-stock-type">{stock.board_type}</span>}
            {stock.themes[0] && <span className="sentiment-matrix-stock-theme">{stock.themes[0]}</span>}
          </div>
          <code>
            {stock.code}
            {stock.limit_time ? ` · ${formatLimitTime(stock.limit_time)}涨停` : ""}
          </code>
        </button>
      </Tooltip>
    );
  };

  return (
    <>
      <div className="sentiment-matrix-stock-list">
        {visibleStocks.map(renderCard)}
        {hiddenCount > 0 && (
        <button
          type="button"
          className="sentiment-matrix-stock-more"
          onClick={() => setExpanded(true)}
        >
          还有 {hiddenCount} 只，查看全部
        </button>
        )}
      </div>
      <Modal
        open={expanded}
        title={`${dayjs(tradeDate).format("MM月DD日")} · ${boardCount}板 · 全部 ${stocks.length} 只`}
        width={920}
        footer={null}
        destroyOnClose
        onCancel={() => setExpanded(false)}
      >
        <div className="sentiment-matrix-stock-modal-grid">{stocks.map(renderCard)}</div>
      </Modal>
    </>
  );
}

function NegativeFeedbackCards({
  stocks,
  tradeDate,
  onOpen,
}: {
  stocks: SentimentNegativeFeedbackItem[];
  tradeDate: string;
  onOpen: (target: StockKlineTarget) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!stocks.length) return <Text type="secondary">—</Text>;
  const visibleStocks = stocks.slice(0, 4);
  const hiddenCount = stocks.length - visibleStocks.length;
  const renderCard = (stock: SentimentNegativeFeedbackItem) => (
    <button
      key={`${tradeDate}:${stock.code}`}
      type="button"
      className="sentiment-negative-stock-card"
      onClick={() => onOpen({ code: stock.code, name: stock.name, signalDate: tradeDate })}
      title={`近10个交易日最高${stock.recent_max_board}板，今日跌停`}
    >
      <div className="sentiment-matrix-stock-title">
        <strong>{stock.name || stock.code}</strong>
        <span className="sentiment-negative-board-tag">曾{stock.recent_max_board}板</span>
      </div>
      <code>{stock.code} · {dayjs(stock.recent_board_date).format("MM-DD")}高标</code>
    </button>
  );
  return (
    <>
      <div className="sentiment-matrix-stock-list">
        {visibleStocks.map(renderCard)}
        {hiddenCount > 0 && (
          <button type="button" className="sentiment-matrix-stock-more" onClick={() => setExpanded(true)}>
            还有 {hiddenCount} 只，查看全部
          </button>
        )}
      </div>
      <Modal
        open={expanded}
        title={`${dayjs(tradeDate).format("MM月DD日")} · 负反馈 · 全部 ${stocks.length} 只`}
        width={920}
        footer={null}
        destroyOnClose
        onCancel={() => setExpanded(false)}
      >
        <div className="sentiment-matrix-stock-modal-grid">{stocks.map(renderCard)}</div>
      </Modal>
    </>
  );
}

function MatrixView({
  items,
  loading,
  loadingMore,
  hasMore,
  onLoadMore,
  onSelectDate,
  onOpenStock,
}: {
  items: SentimentDay[];
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  onLoadMore: () => Promise<unknown>;
  onSelectDate: (date: string) => void;
  onOpenStock: (target: StockKlineTarget) => void;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const initializedScrollRef = useRef(false);
  const prependAnchorRef = useRef<{ scrollLeft: number; scrollWidth: number } | null>(null);
  const virtualFrameRef = useRef<number | null>(null);
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 12 });

  const updateVisibleRange = useCallback((element: HTMLDivElement) => {
    const firstVisible = Math.max(
      0,
      Math.floor(Math.max(0, element.scrollLeft - MATRIX_LABEL_WIDTH) / MATRIX_COLUMN_WIDTH)
    );
    const viewportColumns = Math.ceil(element.clientWidth / MATRIX_COLUMN_WIDTH);
    const next = {
      start: Math.max(0, firstVisible - MATRIX_OVERSCAN_COLUMNS),
      end: Math.min(
        items.length,
        firstVisible + viewportColumns + MATRIX_OVERSCAN_COLUMNS
      ),
    };
    setVisibleRange((current) => (
      current.start === next.start && current.end === next.end ? current : next
    ));
  }, [items.length]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !items.length) return;
    const frame = window.requestAnimationFrame(() => {
      if (!initializedScrollRef.current) {
        element.scrollLeft = element.scrollWidth;
        initializedScrollRef.current = true;
        updateVisibleRange(element);
        return;
      }
      const anchor = prependAnchorRef.current;
      if (anchor) {
        element.scrollLeft = anchor.scrollLeft + element.scrollWidth - anchor.scrollWidth;
        prependAnchorRef.current = null;
      }
      updateVisibleRange(element);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [items.length, updateVisibleRange]);

  useEffect(() => () => {
    if (virtualFrameRef.current != null) {
      window.cancelAnimationFrame(virtualFrameRef.current);
    }
  }, []);

  const handleMatrixScroll = (event: UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    if (virtualFrameRef.current == null) {
      virtualFrameRef.current = window.requestAnimationFrame(() => {
        virtualFrameRef.current = null;
        updateVisibleRange(element);
      });
    }
    if (
      !initializedScrollRef.current
      || element.scrollLeft > MATRIX_LOAD_THRESHOLD
      || !hasMore
      || loadingMore
      || prependAnchorRef.current
    ) {
      return;
    }
    prependAnchorRef.current = {
      scrollLeft: element.scrollLeft,
      scrollWidth: element.scrollWidth,
    };
    void onLoadMore().catch(() => {
      prependAnchorRef.current = null;
    });
  };

  const visibleItems = useMemo(
    () => items.slice(visibleRange.start, visibleRange.end),
    [items, visibleRange]
  );

  const leaderPathKeys = useMemo(
    () => {
      const timelineByCode = new Map<string, Array<{ tradeDate: string; item: SentimentLadderItem }>>();
      for (const day of items) {
        for (const item of day.ladder.items) {
          const timeline = timelineByCode.get(item.code) ?? [];
          timeline.push({ tradeDate: day.trade_date, item });
          timelineByCode.set(item.code, timeline);
        }
      }

      const keys = new Set<string>();
      for (const timeline of timelineByCode.values()) {
        timeline.sort((left, right) => left.tradeDate.localeCompare(right.tradeDate));
        timeline.forEach((point, highIndex) => {
          if ((point.item.continuous_board_count ?? 0) < 6) return;
          let originIndex = -1;
          for (let index = highIndex; index >= 0; index -= 1) {
            if (timeline[index].item.continuous_board_count === 1) {
              originIndex = index;
              break;
            }
          }
          const startIndex = originIndex >= 0 ? originIndex : 0;
          for (let index = startIndex; index <= highIndex; index += 1) {
            const stage = timeline[index];
            if ([1, 2, 3, 4, 5].includes(stage.item.continuous_board_count ?? 0)) {
              keys.add(`${stage.tradeDate}:${stage.item.code}`);
            }
          }
        });
      }
      return keys;
    },
    [items]
  );
  const rows = useMemo(
    () => [
      {
        key: "index",
        label: "上证指数",
        render: (day: SentimentDay) => (
          <span className={`sentiment-metric-bold ${(day.market.sh_change_pct ?? 0) >= 0 ? "sentiment-metric-red" : "sentiment-metric-green"}`}>
            {formatPct(day.market.sh_change_pct)}
          </span>
        ),
      },
      { key: "up", label: "涨家数", render: (day: SentimentDay) => <span className="sentiment-metric-red">{day.market.up_count ?? "—"}</span> },
      { key: "down", label: "跌家数", render: (day: SentimentDay) => <span className="sentiment-metric-green">{day.market.down_count ?? "—"}</span> },
      {
        key: "amount",
        label: "市场量能",
        render: (day: SentimentDay) => (
          <span>{formatAmount(day.market.total_amount)}{day.market.amount_change_pct != null ? `（${formatPct(day.market.amount_change_pct)}）` : ""}</span>
        ),
      },
      {
        key: "limit-themes",
        label: "涨停题材",
        render: (day: SentimentDay) => <ThemeList items={day.limit_up_themes} />,
      },
      {
        key: "limit-down",
        label: "跌停数量",
        render: (day: SentimentDay) => <span className="sentiment-metric-green">{day.market.limit_down_count ?? "—"}</span>,
      },
      {
        key: "new-high",
        label: "百日新高",
        render: (day: SentimentDay) => <ThemeList items={day.new_high_themes} />,
      },
      {
        key: "strong-sectors",
        label: "强势板块",
        render: (day: SentimentDay) => <SectorList items={day.strong_sectors} tone="strong" />,
      },
      {
        key: "weak-sectors",
        label: "弱势板块",
        render: (day: SentimentDay) => <SectorList items={day.weak_sectors} tone="weak" />,
      },
      {
        key: "height",
        label: "高度板",
        render: (day: SentimentDay) =>
          <span className="sentiment-metric-bold">{day.ladder.max_board ? `${day.ladder.max_board}板` : "—"}</span>,
      },
      ...[6, 5, 4, 3, 2].map((height) => ({
        key: `board-${height}`,
        label: height === 6 ? "6板+" : `${height}板`,
        render: (day: SentimentDay) => {
          const stocks = day.ladder.items.filter((item) =>
            height === 6
              ? (item.continuous_board_count ?? 0) >= 6
              : item.continuous_board_count === height
          );
          return (
            <MatrixStockCards
              stocks={stocks}
              tradeDate={day.trade_date}
              onOpen={onOpenStock}
              highlightKeys={height < 6 ? leaderPathKeys : undefined}
            />
          );
        },
      })),
      {
        key: "first",
        label: "主要首板",
        render: (day: SentimentDay) => {
          const stocks = day.ladder.items.filter((item) => item.is_major_first_board);
          return (
            <MatrixStockCards
              stocks={stocks}
              tradeDate={day.trade_date}
              onOpen={onOpenStock}
              highlightKeys={leaderPathKeys}
            />
          );
        },
      },
      {
        key: "all-first",
        label: "全部首板",
        render: (day: SentimentDay) => (
          <MatrixStockCards
            stocks={day.ladder.items.filter((item) => item.continuous_board_count === 1)}
            tradeDate={day.trade_date}
            onOpen={onOpenStock}
            highlightKeys={leaderPathKeys}
          />
        ),
      },
      {
        key: "negative",
        label: "负反馈",
        render: (day: SentimentDay) => (
          <NegativeFeedbackCards
            stocks={day.negative_feedback}
            tradeDate={day.trade_date}
            onOpen={onOpenStock}
          />
        ),
      },
    ],
    [leaderPathKeys, onOpenStock]
  );

  const columns = useMemo(
    () => {
      const leftSpacerWidth = visibleRange.start * MATRIX_COLUMN_WIDTH;
      const rightSpacerWidth = (items.length - visibleRange.end) * MATRIX_COLUMN_WIDTH;
      return [
        {
        title: "指标",
        dataIndex: "label",
        key: "label",
        width: MATRIX_LABEL_WIDTH,
        fixed: "left" as const,
        className: "sentiment-matrix-label",
        },
        ...(leftSpacerWidth > 0 ? [{
          title: null,
          key: "virtual-left-spacer",
          width: leftSpacerWidth,
          className: "sentiment-matrix-spacer",
          render: () => null,
        }] : []),
        ...visibleItems.map((day) => ({
        title: (
          <Button type="link" size="small" onClick={() => onSelectDate(day.trade_date)}>
            {dayjs(day.trade_date).format("MM月DD日")}
          </Button>
        ),
        key: day.trade_date,
        width: 168,
        render: (_: unknown, row: (typeof rows)[number]) => (
          <div className="sentiment-matrix-cell">{row.render(day)}</div>
        ),
        })),
        ...(rightSpacerWidth > 0 ? [{
          title: null,
          key: "virtual-right-spacer",
          width: rightSpacerWidth,
          className: "sentiment-matrix-spacer",
          render: () => null,
        }] : []),
      ];
    },
    [items.length, onSelectDate, rows, visibleItems, visibleRange]
  );

  if (!loading && items.length === 0) {
    return <Empty description="尚无情绪周期快照，请切换到单日视图同步一个交易日" />;
  }
  return (
    <div className="sentiment-matrix-shell">
      {loadingMore && (
        <div className="sentiment-matrix-history-status">
          <Spin size="small" /> 正在加载更早的 30 个交易日…
        </div>
      )}
      <Table
        wrapperRef={scrollRef}
        onScroll={handleMatrixScroll}
        className="sentiment-matrix"
        loading={loading}
        rowKey="key"
        columns={columns}
        dataSource={rows}
        pagination={false}
        bordered
        size="small"
        scroll={{ x: Math.max(900, MATRIX_LABEL_WIDTH + items.length * MATRIX_COLUMN_WIDTH) }}
      />
    </div>
  );
}

function LadderStock({
  item,
  tradeDate,
  onOpen,
}: {
  item: SentimentLadderItem;
  tradeDate: string;
  onOpen: (target: StockKlineTarget) => void;
}) {
  const primaryTheme = item.themes[0];
  return (
    <div className="sentiment-ladder-stock-card">
      {primaryTheme && <span className="sentiment-ladder-primary-theme">{primaryTheme}</span>}
      <div className="sentiment-ladder-stock-head">
        <Button
          type="link"
          size="small"
          onClick={() => onOpen({ code: item.code, name: item.name, signalDate: tradeDate })}
        >
          {item.name || item.code}
        </Button>
        {item.board_type && <Tag color="orange">{item.board_type}</Tag>}
      </div>
      <Text type="secondary" code>
        {item.code}{item.limit_time ? ` · 涨停 ${formatLimitTime(item.limit_time)}` : ""}
      </Text>
      {item.themes.length > 1 && (
        <div className="sentiment-ladder-theme-list">
          {item.themes.slice(1, 4).map((theme) => <Tag key={theme} color="blue">{theme}</Tag>)}
        </div>
      )}
      {item.reason && <Paragraph className="sentiment-ladder-reason">{item.reason}</Paragraph>}
      <div className="sentiment-ladder-card-foot">{sourceTag(item.source)}</div>
    </div>
  );
}

export default function SentimentCyclePage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [view, setView] = useState<"matrix" | "day">("matrix");
  const [selectedDate, setSelectedDate] = useState(nowBeijing().format("YYYY-MM-DD"));
  const [majorCodes, setMajorCodes] = useState<string[]>([]);
  const [klineTarget, setKlineTarget] = useState<StockKlineTarget | null>(null);

  const matrixQ = useInfiniteQuery({
    queryKey: ["sentiment-matrix"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => fetchSentimentMatrix(MATRIX_PAGE_SIZE, pageParam ?? undefined),
    getNextPageParam: (lastPage) => (
      lastPage.length === MATRIX_PAGE_SIZE
        ? dayjs(lastPage[0].trade_date).subtract(1, "day").format("YYYY-MM-DD")
        : undefined
    ),
  });
  const matrixItems = useMemo(() => {
    const byDate = new Map<string, SentimentDay>();
    for (const page of matrixQ.data?.pages ?? []) {
      for (const day of page) byDate.set(day.trade_date, day);
    }
    return [...byDate.values()].sort((left, right) => left.trade_date.localeCompare(right.trade_date));
  }, [matrixQ.data?.pages]);
  const loadMoreMatrix = async () => {
    const result = await matrixQ.fetchNextPage();
    if (result.isError) {
      message.error(result.error instanceof Error ? result.error.message : "更早数据加载失败");
      throw result.error;
    }
    return result;
  };
  const dayQ = useQuery({
    queryKey: ["sentiment-day", selectedDate],
    queryFn: () => fetchSentimentDay(selectedDate),
    enabled: view === "day",
  });

  useEffect(() => {
    setMajorCodes(
      dayQ.data?.ladder.items
        .filter((item) => item.is_major_first_board)
        .map((item) => item.code) ?? []
    );
  }, [dayQ.data]);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["sentiment-day"] }),
      queryClient.invalidateQueries({ queryKey: ["sentiment-matrix"] }),
    ]);
  };

  const syncMut = useMutation({
    mutationFn: (force: boolean) => syncSentimentLatest(force),
    onSuccess: async (result) => {
      setSelectedDate(result.latest_trade_date);
      await invalidate();
      if (result.synced_days > 0) {
        const networkText = result.network_requests > 0
          ? `，外部请求 ${result.network_requests} 次并已缓存`
          : "";
        message.success(`已处理 ${result.synced_days} 个缺失或外部不完整交易日，最新 ${result.latest_trade_date}${networkText}`);
      } else {
        message.success(`最近 ${result.window_days} 个交易日数据已完整，最新 ${result.latest_trade_date}`);
      }
    },
    onError: (error: Error) => message.error(error.message),
  });

  const majorMut = useMutation({
    mutationFn: () => updateMajorFirstBoards(selectedDate, majorCodes),
    onSuccess: async () => {
      await invalidate();
      message.success("主要首板已保存");
    },
    onError: (error: Error) => message.error(error.message),
  });

  const selectDay = (date: string) => {
    setSelectedDate(date);
    setView("day");
  };

  const day = dayQ.data;
  const ladderGroups = useMemo(() => {
    const groups = new Map<number, SentimentLadderItem[]>();
    for (const item of day?.ladder.items ?? []) {
      const height = item.continuous_board_count ?? 0;
      if (height < 2) continue;
      const list = groups.get(height) ?? [];
      list.push(item);
      groups.set(height, list);
    }
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }, [day]);
  const firstBoards = day?.ladder.items.filter((item) => item.continuous_board_count === 1) ?? [];

  return (
    <div className="sentiment-page">
      <Space className="sentiment-page-header" align="start" wrap>
        <div>
          <Title level={3} style={{ margin: 0 }}>连板梯队</Title>
          <Text type="secondary">本地行情优先 · 外部数据每日一次缓存 · 主观判断人工确认</Text>
        </div>
        <Space wrap>
          <Segmented
            value={view}
            options={[{ label: "矩阵视图", value: "matrix" }, { label: "单日视图", value: "day" }]}
            onChange={(value) => setView(value as "matrix" | "day")}
          />
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            loading={syncMut.isPending}
            onClick={() => syncMut.mutate(false)}
          >
            同步至最新
          </Button>
          <Popconfirm
            title="重新同步最近 30 个交易日？"
            description="将重新计算本地数据，并重新访问已配置的外部数据源。"
            onConfirm={() => syncMut.mutate(true)}
          >
            <Button icon={<ReloadOutlined />} loading={syncMut.isPending}>重建近 30 日</Button>
          </Popconfirm>
        </Space>
      </Space>

      {view === "matrix" && (
        <Card>
          <MatrixView
            items={matrixItems}
            loading={matrixQ.isLoading}
            loadingMore={matrixQ.isFetchingNextPage}
            hasMore={matrixQ.hasNextPage}
            onLoadMore={loadMoreMatrix}
            onSelectDate={selectDay}
            onOpenStock={setKlineTarget}
          />
        </Card>
      )}

      {view === "day" && (
        <>
          <Card className="sentiment-toolbar">
            <Space wrap>
              <ChineseDatePicker
                allowClear={false}
                value={dayjs(selectedDate)}
                onChange={(value) => value && setSelectedDate(value.format("YYYY-MM-DD"))}
              />
              <Text type="secondary">日期仅用于查看历史快照；同步始终补齐本地行情最新 30 个交易日</Text>
            </Space>
          </Card>

          {dayQ.isLoading && <Card><Spin /></Card>}
          {!dayQ.isLoading && !day && (
            <Card><Empty description="该日期尚无快照"><Button type="primary" loading={syncMut.isPending} onClick={() => syncMut.mutate(false)}>同步至最新</Button></Empty></Card>
          )}

          {day && (
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              {day.sync_status.sync_error && <Alert type="warning" showIcon message="部分数据同步失败" description={day.sync_status.sync_error} />}

              <Row gutter={[12, 12]}>
                <Col xs={12} md={4}><Card><Statistic title="上证指数" value={formatPct(day.market.sh_change_pct)} valueStyle={{ color: (day.market.sh_change_pct ?? 0) >= 0 ? "#cf1322" : "#389e0d" }} /></Card></Col>
                <Col xs={12} md={4}><Card><Statistic title="市场量能" value={formatAmount(day.market.total_amount)} suffix={day.market.amount_change_pct != null ? <Text type={day.market.amount_change_pct >= 0 ? "danger" : "success"}>{formatPct(day.market.amount_change_pct)}</Text> : undefined} /></Card></Col>
                <Col xs={12} md={4}><Card><Statistic title="涨 / 跌家数" value={`${day.market.up_count ?? "—"} / ${day.market.down_count ?? "—"}`} /></Card></Col>
                <Col xs={12} md={4}><Card><Statistic title="涨停 / 跌停" value={`${day.market.limit_up_count ?? "—"} / ${day.market.limit_down_count ?? "—"}`} /></Card></Col>
                <Col xs={12} md={4}><Card><Statistic title="百日新高" value={day.market.new_high_100_count ?? "—"} suffix="只" /></Card></Col>
                <Col xs={12} md={4}><Card><Statistic title="3板" value={day.ladder.three_board_count} suffix="只" /></Card></Col>
              </Row>

              <Card title="数据状态" size="small">
                <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }}>
                  <Descriptions.Item label="本地计算"><Tag color={day.sync_status.local_complete ? "success" : "warning"}>{day.sync_status.local_complete ? "完成" : "不完整"}</Tag></Descriptions.Item>
                  <Descriptions.Item label="外部增强"><Tag color={day.sync_status.external_status === "complete" ? "success" : "default"}>{EXTERNAL_STATUS_LABEL[day.sync_status.external_status] ?? day.sync_status.external_status}</Tag></Descriptions.Item>
                  <Descriptions.Item label="外部配置">{day.sync_status.external_configured ? "已配置" : "未配置"}</Descriptions.Item>
                  <Descriptions.Item label="更新时间">{parseApiTime(day.sync_status.updated_at).format("YYYY-MM-DD HH:mm")}</Descriptions.Item>
                </Descriptions>
              </Card>

              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card title="涨停题材 Top 3" extra={day.limit_up_themes[0] && sourceTag(day.limit_up_themes[0].source)}><ThemeList items={day.limit_up_themes} />{!day.limit_up_themes.length && <Paragraph type="secondary" style={{ marginTop: 8 }}>需要开盘啦题材缓存；基础涨停数量仍由本地数据提供。</Paragraph>}</Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="百日新高题材 Top 3" extra={day.new_high_themes[0] && sourceTag(day.new_high_themes[0].source)}><ThemeList items={day.new_high_themes} />{!day.new_high_themes.length && <Paragraph type="secondary" style={{ marginTop: 8 }}>本地已识别 {day.new_high_stocks.length} 只创新高股票；当日没有与开盘啦题材缓存重合的股票。</Paragraph>}</Card>
                </Col>
              </Row>

              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card title="强势板块 Top 5" extra={day.strong_sectors[0] && sourceTag(day.strong_sectors[0].source)}>
                    <SectorList items={day.strong_sectors} tone="strong" />
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="弱势板块 Bottom 5" extra={day.weak_sectors[0] && sourceTag(day.weak_sectors[0].source)}>
                    <SectorList items={day.weak_sectors} tone="weak" />
                  </Card>
                </Col>
              </Row>

              <Card title={`连板梯队 · 高度 ${day.ladder.max_board || "—"} 板`}>
                {ladderGroups.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无连板数据" />}
                {ladderGroups.map(([height, items]) => (
                  <div key={height} className="sentiment-ladder-group">
                    <div className="sentiment-ladder-title">
                      <Tag color={height >= 4 ? "red" : "cyan"}>{height}板</Tag>
                      <Text type="secondary">{items.length}只</Text>
                      <Text type="secondary" className="sentiment-ladder-count">连板数 {height}</Text>
                    </div>
                    <div className="sentiment-ladder-grid">{items.map((item) => <LadderStock key={item.id} item={item} tradeDate={selectedDate} onOpen={setKlineTarget} />)}</div>
                  </div>
                ))}
              </Card>

              <Card title="主要首板" extra={<Button loading={majorMut.isPending} onClick={() => majorMut.mutate()}>保存调整</Button>}>
                <Paragraph type="secondary">三板股形成后，系统会自动回填到它最近一次首板日期；这里仍可手动补充或调整。</Paragraph>
                {firstBoards.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无首板数据" /> : (
                  <Checkbox.Group className="sentiment-first-board-picker" value={majorCodes} onChange={(values) => setMajorCodes(values as string[])} style={{ width: "100%" }}>
                    <Row gutter={[8, 8]}>{firstBoards.map((item) => <Col xs={24} md={12} lg={8} key={item.id}><Checkbox value={item.code}><Tooltip title={item.reason}>{item.name || item.code} {item.themes.length ? `（${item.themes.join("+")}）` : ""}</Tooltip></Checkbox></Col>)}</Row>
                  </Checkbox.Group>
                )}
              </Card>

              <Card title="负反馈 · 近10个交易日曾进入3板+后跌停">
                <NegativeFeedbackCards
                  stocks={day.negative_feedback}
                  tradeDate={selectedDate}
                  onOpen={setKlineTarget}
                />
              </Card>
            </Space>
          )}
        </>
      )}

      <StockKlineModal open={!!klineTarget} stock={klineTarget} onClose={() => setKlineTarget(null)} />
    </div>
  );
}
