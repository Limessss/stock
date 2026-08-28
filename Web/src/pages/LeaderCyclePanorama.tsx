import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent as ReactDragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs, { type Dayjs } from "dayjs";
import ReactECharts from "echarts-for-react";
import {
  CalendarDays,
  CalendarRange,
  FolderOpen,
  GripVertical,
  Plus,
  RotateCcw,
  Save,
  Search,
  Trash2,
  TrendingUp,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getKline } from "@/api/kline";
import {
  createPanoramaPreset,
  deletePanoramaPreset,
  getPanoramaConfig,
  listPanoramaPresets,
  savePanoramaConfig,
  updatePanoramaPreset,
  type PanoramaInstrumentRecord,
  type PanoramaPresetRecord,
} from "@/api/panorama";
import { searchStocks, type StockSearchItem } from "@/api/stocks";
import ChineseDatePicker from "@/components/ChineseDatePicker";
import KlineChart, {
  type KlineSelectedRange,
  type KlineVisibleRange,
} from "@/components/KlineChart";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Spin,
  Tag,
  Typography,
  message,
} from "@/components/ui";

const { Title, Text } = Typography;
const STORAGE_KEY = "stockmodel.leader-cycle-panorama.v1";
const VIEW_STORAGE_KEY = "stockmodel.leader-cycle-panorama.view.v1";
const YEAR_BARS = 252;
const MAX_INSTRUMENTS = 100;
const MAX_OVERLAY_INSTRUMENTS = 20;

type PanoramaInstrument = PanoramaInstrumentRecord;

interface PanoramaRange {
  start: string;
  end: string;
}

type PanoramaViewMode = "detail" | "grid" | "overlay";
type OverlayYAxisMode = "focus" | "auto";

interface OverlayPoint {
  value: number;
  dailyChange: number | null;
}

interface OverlayTooltipParam {
  axisValue: string;
  marker: string;
  seriesName: string;
  data: OverlayPoint | null;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char] ?? char);
}

const INDEX_OPTIONS: PanoramaInstrument[] = [
  { code: "SH000001", name: "上证指数", type: "index" },
  { code: "SZ399001", name: "深证成指", type: "index" },
  { code: "SH000300", name: "沪深300", type: "index" },
  { code: "SZ399006", name: "创业板指", type: "index" },
  { code: "SH000688", name: "科创50", type: "index" },
  { code: "SH000016", name: "上证50", type: "index" },
  { code: "SH000905", name: "中证500", type: "index" },
  { code: "SH000852", name: "中证1000", type: "index" },
  { code: "SZ399303", name: "国证2000", type: "index" },
];

const DEFAULT_INSTRUMENTS = INDEX_OPTIONS.slice(0, 2);

function loadSavedInstruments(): PanoramaInstrument[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_INSTRUMENTS;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_INSTRUMENTS;
    return parsed
      .filter((item) => item && typeof item.code === "string" && typeof item.name === "string")
      .slice(0, MAX_INSTRUMENTS)
      .map((item) => ({
        code: item.code.toUpperCase(),
        name: item.name,
        type: item.type === "index" ? "index" : "stock",
      }));
  } catch {
    return DEFAULT_INSTRUMENTS;
  }
}

function normalizeCode(code: string): string {
  return code.trim().toUpperCase();
}

function isIndexCode(code: string): boolean {
  return code.startsWith("SH000") || code.startsWith("SZ399");
}

function gainPct(first?: number, last?: number): number | null {
  if (first == null || last == null || first <= 0) return null;
  return ((last - first) / first) * 100;
}

function klineOptions(range: PanoramaRange | null) {
  if (!range) return { lastN: YEAR_BARS };
  return { lastN: YEAR_BARS, endDate: range.end, minDate: range.start };
}

function LazyPanoramaChartSlot({ compact, children }: { compact: boolean; children: ReactNode }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || ready) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setReady(true);
      observer.disconnect();
    }, { rootMargin: "700px 0px" });
    observer.observe(host);
    return () => observer.disconnect();
  }, [ready]);

  return (
    <div
      ref={hostRef}
      className={`panorama-lazy-slot${ready ? " is-ready" : ""}`}
      style={{ minHeight: compact ? 276 : 342 }}
    >
      {ready ? children : <div className="panorama-lazy-placeholder"><Spin /><Text type="secondary">等待进入视窗…</Text></div>}
    </div>
  );
}

interface ChartRowProps {
  instrument: PanoramaInstrument;
  index: number;
  timeDomain: string[];
  syncDate: string | null;
  syncVisibleRange: KlineVisibleRange | null;
  activeRange: PanoramaRange | null;
  onHoverDate: (date: string | null) => void;
  onVisibleRangeChange: (range: KlineVisibleRange) => void;
  onRangeSelect: (range: KlineSelectedRange) => void;
  onRemove: (code: string) => void;
  isDragging: boolean;
  isDropTarget: boolean;
  onDragStart: (index: number) => void;
  onDragEnter: (index: number) => void;
  onDrop: (index: number) => void;
  onDragEnd: () => void;
  compact: boolean;
}

function PanoramaChartRow({
  instrument,
  index,
  timeDomain,
  syncDate,
  syncVisibleRange,
  activeRange,
  onHoverDate,
  onVisibleRangeChange,
  onRangeSelect,
  onRemove,
  isDragging,
  isDropTarget,
  onDragStart,
  onDragEnter,
  onDrop,
  onDragEnd,
  compact,
}: ChartRowProps) {
  const query = useQuery({
    queryKey: [
      "leader-cycle-panorama",
      instrument.code,
      YEAR_BARS,
      activeRange?.start ?? "recent",
      activeRange?.end ?? "latest",
    ],
    queryFn: () => getKline(instrument.code, klineOptions(activeRange)),
    staleTime: 10 * 60_000,
  });
  const candles = query.data?.candles ?? [];
  const domainStart = timeDomain[0];
  const domainEnd = timeDomain[timeDomain.length - 1];
  const visibleCandles = domainStart && domainEnd
    ? candles.filter((bar) => bar.time >= domainStart && bar.time <= domainEnd)
    : candles;
  const first = visibleCandles[0];
  const last = visibleCandles[visibleCandles.length - 1];
  const periodGain = gainPct(first?.close, last?.close);
  const displayName = query.data?.name || instrument.name || instrument.code;
  const chartHeight = compact ? 230 : 340;

  const instrumentInfo = (
    <div className="panorama-instrument-title">
      <strong>{displayName}</strong>
      <div className="panorama-instrument-meta">
        <Text code>{instrument.code}</Text>
      </div>
      {periodGain != null && (
        <div className="panorama-period-gain">
          <Text type="secondary">区间涨幅</Text>
          <strong className={periodGain >= 0 ? "panorama-gain-positive" : "panorama-gain-negative"}>
            {periodGain > 0 ? "+" : ""}{periodGain.toFixed(2)}%
          </strong>
        </div>
      )}
    </div>
  );

  const rowActions = (
    <div className="panorama-row-actions">
      <button
        type="button"
        className="qd-button panorama-drag-handle"
        draggable
        aria-label={`拖动排序：${displayName}`}
        aria-grabbed={isDragging}
        title="按住并拖到目标股票位置"
        onDragStart={(event: ReactDragEvent<HTMLButtonElement>) => {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", instrument.code);
          onDragStart(index);
        }}
        onDragEnd={onDragEnd}
      >
        <GripVertical size={16} />
      </button>
      <Button
        danger
        aria-label="删除"
        title="删除"
        icon={<Trash2 size={15} />}
        onClick={() => onRemove(instrument.code)}
      />
    </div>
  );

  const chartContent = (
    <div className="panorama-chart-main">
      {query.isLoading && <div className="panorama-chart-state" style={{ height: chartHeight }}><Spin size="large" /><Text type="secondary">正在读取本地日K…</Text></div>}
      {query.error && (
        <Alert
          type="error"
          message={`${displayName} K线读取失败`}
          description={(query.error as Error).message}
        />
      )}
      {query.data && candles.length > 0 && (
        <KlineChart
          data={query.data}
          height={chartHeight}
          visibleBars={YEAR_BARS}
          focusDate={domainEnd || last?.time}
          timeDomain={timeDomain}
          syncDate={syncDate}
          onHoverDate={onHoverDate}
          syncVisibleRange={syncVisibleRange}
          onVisibleRangeChange={onVisibleRangeChange}
          onRangeSelect={onRangeSelect}
          showVolume={!compact}
          showMacd={false}
        />
      )}
      {query.data && candles.length === 0 && <Empty description="本地没有该证券的日K数据" />}
    </div>
  );

  return (
    <Card
      className={`panorama-chart-card${compact ? " is-compact" : ""}${isDragging ? " is-dragging" : ""}${isDropTarget ? " is-drop-target" : ""}`}
      onDragEnter={() => onDragEnter(index)}
      onDragOver={(event: ReactDragEvent<HTMLElement>) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      }}
      onDrop={(event: ReactDragEvent<HTMLElement>) => {
        event.preventDefault();
        onDrop(index);
      }}
    >
      {compact ? (
        <>
          <div className="panorama-chart-head">
            {instrumentInfo}
            {rowActions}
          </div>
          {chartContent}
        </>
      ) : (
        <div className="panorama-detail-layout">
          <aside className="panorama-chart-sidebar">
            {instrumentInfo}
            {rowActions}
          </aside>
          {chartContent}
        </div>
      )}
    </Card>
  );
}

export default function LeaderCyclePanoramaPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [instruments, setInstruments] = useState<PanoramaInstrument[]>(loadSavedInstruments);
  const [searchValue, setSearchValue] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [draftStart, setDraftStart] = useState<string>();
  const [draftEnd, setDraftEnd] = useState<string>();
  const [activeRange, setActiveRange] = useState<PanoramaRange | null>(null);
  const [syncDate, setSyncDate] = useState<string | null>(null);
  const [syncVisibleRange, setSyncVisibleRange] = useState<KlineVisibleRange | null>(null);
  const [rangeMenu, setRangeMenu] = useState<KlineSelectedRange | null>(null);
  const [selectedPresetId, setSelectedPresetId] = useState<string>();
  const [loadedPresetId, setLoadedPresetId] = useState<string>();
  const [saveRange, setSaveRange] = useState<PanoramaRange | null>(null);
  const [presetName, setPresetName] = useState("");
  const [viewMode, setViewMode] = useState<PanoramaViewMode>(() => {
    const saved = window.localStorage.getItem(VIEW_STORAGE_KEY);
    return saved === "detail" || saved === "overlay" ? saved : "grid";
  });
  const [gridColumns, setGridColumns] = useState<2 | 3>(2);
  const [overlayHeight, setOverlayHeight] = useState<720 | 1000 | 1400 | 1800>(1000);
  const [overlayYAxisMode, setOverlayYAxisMode] = useState<OverlayYAxisMode>("focus");
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [databaseReady, setDatabaseReady] = useState(false);
  const [databaseSaveError, setDatabaseSaveError] = useState("");
  const localSeedRef = useRef<PanoramaInstrument[]>(instruments);
  const lastDatabaseValueRef = useRef("");
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());

  const configQuery = useQuery({
    queryKey: ["leader-cycle-panorama-config", 1],
    queryFn: async () => {
      const stored = await getPanoramaConfig();
      if (stored.initialized) return stored;
      // 数据库首次启用：把当前浏览器已经添加的列表原样迁移过去。
      return savePanoramaConfig(localSeedRef.current);
    },
    staleTime: Infinity,
    retry: 3,
  });

  const calendarQuery = useQuery({
    queryKey: [
      "leader-cycle-panorama",
      "SH000001",
      YEAR_BARS,
      activeRange?.start ?? "recent",
      activeRange?.end ?? "latest",
    ],
    queryFn: () => getKline("SH000001", klineOptions(activeRange)),
    staleTime: 10 * 60_000,
  });
  const timeDomain = useMemo(
    () => (calendarQuery.data?.candles ?? [])
      .filter((bar) => !activeRange || (bar.time >= activeRange.start && bar.time <= activeRange.end))
      .map((bar) => bar.time),
    [activeRange, calendarQuery.data?.candles]
  );

  const overlayInstruments = instruments.slice(0, MAX_OVERLAY_INSTRUMENTS);
  const overlayQueries = useQueries({
    queries: overlayInstruments.map((instrument) => ({
      queryKey: [
        "leader-cycle-panorama",
        instrument.code,
        YEAR_BARS,
        activeRange?.start ?? "recent",
        activeRange?.end ?? "latest",
      ],
      queryFn: () => getKline(instrument.code, klineOptions(activeRange)),
      staleTime: 10 * 60_000,
      enabled: viewMode === "overlay",
    })),
  });

  const overlaySeries = useMemo(() => overlayQueries.flatMap((query, index) => {
    const candles = query.data?.candles ?? [];
    const inRange = candles.filter(
      (bar) => timeDomain.length === 0 || (bar.time >= timeDomain[0] && bar.time <= timeDomain[timeDomain.length - 1])
    );
    const base = inRange.find((bar) => bar.close > 0)?.close;
    if (!base) return [];
    const valueByDate = new Map<string, OverlayPoint>(
      inRange.map((bar) => [bar.time, {
        value: Number((((bar.close / base) - 1) * 100).toFixed(2)),
        dailyChange: bar.change_pct == null ? null : Number(bar.change_pct.toFixed(2)),
      }])
    );
    const instrument = overlayInstruments[index];
    return [{
      name: `${instrument.name} ${instrument.code}`,
      type: "line" as const,
      data: timeDomain.map((date) => valueByDate.get(date) ?? null),
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 1.6 },
      emphasis: { focus: "series" as const, lineStyle: { width: 3 } },
    }];
  }), [overlayInstruments, overlayQueries, timeDomain]);

  const overlayFocusBounds = useMemo(() => {
    const values = overlaySeries
      .flatMap((series) => series.data.flatMap((point) => point ? [point.value] : []))
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    if (!values.length) return { min: -20, max: 200 };
    const lower = values[Math.floor((values.length - 1) * 0.02)];
    const upper = values[Math.floor((values.length - 1) * 0.95)];
    const span = Math.max(20, upper - lower);
    return {
      min: Math.floor((lower - span * 0.08) / 10) * 10,
      max: Math.ceil((upper + span * 0.12) / 10) * 10,
    };
  }, [overlaySeries]);

  const overlayOption = useMemo(() => ({
    animation: false,
    backgroundColor: "transparent",
    color: [
      "#4f46e5", "#ef4444", "#0ea5e9", "#f59e0b", "#10b981",
      "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#64748b",
    ],
    legend: { type: "scroll", top: 4, left: 12, right: 12, textStyle: { color: "#64748b", fontSize: 11 } },
    tooltip: {
      trigger: "axis",
      order: "valueDesc",
      formatter: (rawParams: OverlayTooltipParam | OverlayTooltipParam[]) => {
        const params = (Array.isArray(rawParams) ? rawParams : [rawParams])
          .filter((item) => item.data && Number.isFinite(item.data.value))
          .sort((a, b) => (b.data?.value ?? 0) - (a.data?.value ?? 0));
        if (!params.length) return "";
        const rows = params.map((item) => {
          const cumulative = item.data?.value ?? 0;
          const daily = item.data?.dailyChange;
          const dailyText = daily == null ? "—" : `${daily > 0 ? "+" : ""}${daily.toFixed(2)}%`;
          const dailyColor = daily == null ? "#94a3b8" : daily >= 0 ? "#ef4444" : "#16a34a";
          return `<div style="display:grid;grid-template-columns:minmax(150px,1fr) 92px 88px;gap:12px;align-items:center;margin-top:5px"><span>${item.marker}${escapeHtml(item.seriesName)}</span><span style="text-align:right">累计 ${cumulative > 0 ? "+" : ""}${cumulative.toFixed(2)}%</span><span style="color:${dailyColor};text-align:right">当日 ${dailyText}</span></div>`;
        });
        return `<div style="min-width:440px"><strong>${escapeHtml(params[0].axisValue)}</strong><div style="margin-top:7px;color:#94a3b8;font-size:11px;text-align:right">累计涨幅　　当日涨幅</div>${rows.join("")}</div>`;
      },
    },
    grid: { top: 56, left: 62, right: 64, bottom: 72 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: timeDomain,
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { color: "#64748b", hideOverlap: true, formatter: (value: string) => value.slice(5) },
      axisPointer: { show: true, label: { show: true } },
    },
    yAxis: {
      type: "value",
      scale: true,
      ...(overlayYAxisMode === "focus" ? overlayFocusBounds : {}),
      axisLabel: { color: "#64748b", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#e5e7eb", type: "dashed" } },
    },
    dataZoom: [
      { type: "inside", xAxisIndex: 0, filterMode: "none" },
      { type: "slider", xAxisIndex: 0, height: 22, bottom: 22, filterMode: "none" },
      {
        type: "slider",
        yAxisIndex: 0,
        orient: "vertical",
        width: 16,
        right: 8,
        top: 60,
        bottom: 72,
        filterMode: "none",
      },
    ],
    series: overlaySeries,
  }), [overlayFocusBounds, overlaySeries, overlayYAxisMode, timeDomain]);
  const overlayLoading = overlayQueries.some((query) => query.isLoading || query.isFetching);
  const overlayError = overlayQueries.find((query) => query.error)?.error as Error | undefined;

  const presetsQuery = useQuery({
    queryKey: ["leader-cycle-panorama-presets"],
    queryFn: listPanoramaPresets,
    staleTime: 60_000,
  });

  const savePresetMutation = useMutation({
    mutationFn: createPanoramaPreset,
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ["leader-cycle-panorama-presets"] });
      setSelectedPresetId(saved.id);
      setLoadedPresetId(saved.id);
      setSaveRange(null);
      setPresetName("");
      message.success("区间股票列表已保存");
    },
    onError: (error: Error) => message.error(`保存失败：${error.message}`),
  });

  const updatePresetMutation = useMutation({
    mutationFn: ({ id, input }: { id: string; input: Parameters<typeof updatePanoramaPreset>[1] }) => (
      updatePanoramaPreset(id, input)
    ),
    onSuccess: async (saved) => {
      setSelectedPresetId(saved.id);
      setLoadedPresetId(saved.id);
      await queryClient.invalidateQueries({ queryKey: ["leader-cycle-panorama-presets"] });
      message.success(`已保存“${saved.name}”`);
    },
    onError: (error: Error) => message.error(`保存失败：${error.message}`),
  });

  const deletePresetMutation = useMutation({
    mutationFn: deletePanoramaPreset,
    onSuccess: async (_, deletedId) => {
      if (selectedPresetId === deletedId) setSelectedPresetId(undefined);
      if (loadedPresetId === deletedId) setLoadedPresetId(undefined);
      await queryClient.invalidateQueries({ queryKey: ["leader-cycle-panorama-presets"] });
      message.success("区间方案已删除");
    },
    onError: (error: Error) => message.error(`删除失败：${error.message}`),
  });

  const normalizedSearch = searchValue.trim();
  const stockSearch = useQuery({
    queryKey: ["leader-cycle-stock-search", normalizedSearch],
    queryFn: () => searchStocks(normalizedSearch, 12),
    enabled: normalizedSearch.length > 0,
    staleTime: 60_000,
  });

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(instruments));
  }, [instruments]);

  useEffect(() => {
    window.localStorage.setItem(VIEW_STORAGE_KEY, viewMode);
  }, [viewMode]);

  useEffect(() => {
    if (!configQuery.data) return;
    const stored = configQuery.data.instruments.slice(0, MAX_INSTRUMENTS);
    lastDatabaseValueRef.current = JSON.stringify(stored);
    setInstruments(stored);
    setDatabaseReady(true);
    setDatabaseSaveError("");
  }, [configQuery.data]);

  useEffect(() => {
    if (!databaseReady) return;
    const serialized = JSON.stringify(instruments);
    if (serialized === lastDatabaseValueRef.current) return;
    const snapshot = instruments.map((item) => ({ ...item }));
    const timer = window.setTimeout(() => {
      saveQueueRef.current = saveQueueRef.current
        .catch(() => undefined)
        .then(async () => {
          const saved = await savePanoramaConfig(snapshot);
          lastDatabaseValueRef.current = JSON.stringify(saved.instruments);
          setDatabaseSaveError("");
        })
        .catch((error: unknown) => {
          setDatabaseSaveError(error instanceof Error ? error.message : String(error));
        });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [databaseReady, instruments]);

  useEffect(() => {
    if (!rangeMenu) return;
    const closeMenu = (event: MouseEvent) => {
      if ((event.target as HTMLElement | null)?.closest(".panorama-range-menu")) return;
      setRangeMenu(null);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setRangeMenu(null);
    };
    window.addEventListener("mousedown", closeMenu);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("mousedown", closeMenu);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [rangeMenu]);

  const existingCodes = useMemo(() => new Set(instruments.map((item) => item.code)), [instruments]);
  const suggestions = useMemo(() => {
    if (!normalizedSearch) return INDEX_OPTIONS.filter((item) => !existingCodes.has(item.code)).slice(0, 8);
    const q = normalizedSearch.toUpperCase();
    const indices = INDEX_OPTIONS.filter(
      (item) => !existingCodes.has(item.code) && (item.code.includes(q) || item.name.includes(normalizedSearch))
    );
    const stocks = (stockSearch.data ?? [])
      .filter((item) => !existingCodes.has(normalizeCode(item.code)))
      .map<PanoramaInstrument>((item: StockSearchItem) => ({
        code: normalizeCode(item.code),
        name: item.name,
        type: "stock",
      }));
    const merged = [...indices, ...stocks];
    if (/^(SH|SZ)\d{6}$/.test(q) && !existingCodes.has(q) && !merged.some((item) => item.code === q)) {
      merged.unshift({ code: q, name: q, type: isIndexCode(q) ? "index" : "stock" });
    }
    return merged.slice(0, 10);
  }, [existingCodes, normalizedSearch, stockSearch.data]);

  const addInstrument = useCallback((instrument: PanoramaInstrument) => {
    setInstruments((current) => {
      if (current.some((item) => item.code === instrument.code)) return current;
      if (current.length >= MAX_INSTRUMENTS) {
        message.warning(`最多同时展示 ${MAX_INSTRUMENTS} 张K线`);
        return current;
      }
      return [instrument, ...current];
    });
    setSearchValue("");
    setSearchOpen(false);
  }, []);

  const reorderInstrument = useCallback((from: number, to: number) => {
    setInstruments((current) => {
      if (from === to || from < 0 || to < 0 || from >= current.length || to >= current.length) {
        return current;
      }
      const next = [...current];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  }, []);

  const finishDrag = useCallback(() => {
    setDragIndex(null);
    setDragOverIndex(null);
  }, []);

  const dropInstrument = useCallback((targetIndex: number) => {
    if (dragIndex != null) reorderInstrument(dragIndex, targetIndex);
    finishDrag();
  }, [dragIndex, finishDrag, reorderInstrument]);

  const removeInstrument = useCallback((code: string) => {
    setInstruments((current) => current.filter((item) => item.code !== code));
  }, []);

  const handleHoverDate = useCallback((date: string | null) => setSyncDate(date), []);
  const handleVisibleRangeChange = useCallback((range: KlineVisibleRange) => {
    setSyncVisibleRange((current) => (
      current?.from === range.from && current.to === range.to ? current : range
    ));
  }, []);

  const applyRange = useCallback((range: PanoramaRange) => {
    if (range.start > range.end) {
      message.warning("开始日期不能晚于结束日期");
      return false;
    }
    setDraftStart(range.start);
    setDraftEnd(range.end);
    setActiveRange(range);
    setSyncVisibleRange(null);
    setRangeMenu(null);
    return true;
  }, []);

  const applyDraftRange = useCallback(() => {
    if (!draftStart || !draftEnd) {
      message.warning("请选择完整的开始和结束日期");
      return;
    }
    applyRange({ start: draftStart, end: draftEnd });
  }, [applyRange, draftEnd, draftStart]);

  const resetRange = useCallback(() => {
    setDraftStart(undefined);
    setDraftEnd(undefined);
    setActiveRange(null);
    setSyncVisibleRange(null);
    setSelectedPresetId(undefined);
    setLoadedPresetId(undefined);
  }, []);

  const selectedPreset = useMemo(
    () => (presetsQuery.data ?? []).find((item) => item.id === selectedPresetId),
    [presetsQuery.data, selectedPresetId]
  );
  const loadedPreset = useMemo(
    () => (presetsQuery.data ?? []).find((item) => item.id === loadedPresetId),
    [loadedPresetId, presetsQuery.data]
  );

  const loadPreset = useCallback((preset: PanoramaPresetRecord | undefined) => {
    if (!preset) {
      message.warning("请选择要加载的区间方案");
      return;
    }
    setInstruments(preset.instruments.slice(0, MAX_INSTRUMENTS));
    applyRange({ start: preset.start_date, end: preset.end_date });
    setSelectedPresetId(preset.id);
    setLoadedPresetId(preset.id);
    message.success(`已加载“${preset.name}”`);
  }, [applyRange]);

  const openSaveAsDialog = useCallback((range: PanoramaRange) => {
    if (!instruments.length) {
      message.warning("请先添加至少一只股票或指数");
      return;
    }
    setSaveRange(range);
    setPresetName(loadedPreset ? `${loadedPreset.name} 副本` : `${range.start} 至 ${range.end}`);
    setRangeMenu(null);
  }, [instruments.length, loadedPreset]);

  const saveCurrentPreset = useCallback(() => {
    if (!activeRange || !instruments.length) return;
    if (!loadedPreset) {
      openSaveAsDialog(activeRange);
      return;
    }
    updatePresetMutation.mutate({
      id: loadedPreset.id,
      input: {
        name: loadedPreset.name,
        start_date: activeRange.start,
        end_date: activeRange.end,
        instruments,
      },
    });
  }, [activeRange, instruments, loadedPreset, openSaveAsDialog, updatePresetMutation]);

  const submitPreset = useCallback(() => {
    const name = presetName.trim();
    if (!saveRange || !name) {
      message.warning("请输入方案名称");
      return;
    }
    savePresetMutation.mutate({
      name,
      start_date: saveRange.start,
      end_date: saveRange.end,
      instruments,
    });
  }, [instruments, presetName, savePresetMutation, saveRange]);

  return (
    <div className="sentiment-page leader-panorama-page">
      <div className="sentiment-page-header panorama-page-header">
        <div>
          <Title level={3} style={{ margin: 0 }}>龙头周期全景图</Title>
          <Text type="secondary">自定义日期区间 · 保存区间股票列表 · 使用卡片右侧手柄排序 · 多图联动</Text>
        </div>
        <div className={`panorama-sync-date${syncDate ? " is-active" : ""}`}>
          <CalendarDays size={16} />
          <span>{syncDate ? `联动日期 ${syncDate}` : "移动鼠标查看联动日期"}</span>
        </div>
        <div className={`panorama-sync-date panorama-sync-range${activeRange || syncVisibleRange ? " is-active" : ""}`}>
          <span>{activeRange
            ? `自定义区间 ${activeRange.start} — ${activeRange.end}`
            : syncVisibleRange
              ? `联动视窗 ${syncVisibleRange.from} — ${syncVisibleRange.to}`
              : "默认展示最近一年；缩放任一K线可同步视窗"}</span>
        </div>
      </div>

      <Card className="panorama-toolbar">
        <div className="panorama-range-toolbar">
          <div className="panorama-range-fields">
            <Text type="secondary">自定义区间</Text>
            <ChineseDatePicker
              allowClear
              value={draftStart ? dayjs(draftStart) : null}
              maxDate={draftEnd ? dayjs(draftEnd) : undefined}
              placeholder="开始日期"
              onChange={(value: Dayjs | null) => setDraftStart(value?.format("YYYY-MM-DD"))}
            />
            <span className="panorama-range-separator">至</span>
            <ChineseDatePicker
              allowClear
              value={draftEnd ? dayjs(draftEnd) : null}
              minDate={draftStart ? dayjs(draftStart) : undefined}
              placeholder="结束日期"
              onChange={(value: Dayjs | null) => setDraftEnd(value?.format("YYYY-MM-DD"))}
            />
            <Button type="primary" icon={<CalendarRange size={15} />} onClick={applyDraftRange}>应用区间</Button>
            <Button icon={<RotateCcw size={15} />} disabled={!activeRange} onClick={resetRange}>最近一年</Button>
            <Button
              icon={<Save size={15} />}
              loading={updatePresetMutation.isPending}
              disabled={!activeRange || instruments.length === 0 || savePresetMutation.isPending}
              onClick={saveCurrentPreset}
            >保存</Button>
            <Button
              icon={<Plus size={15} />}
              disabled={!activeRange || instruments.length === 0 || updatePresetMutation.isPending}
              onClick={() => activeRange && openSaveAsDialog(activeRange)}
            >另存为</Button>
            <Text type="secondary">当前方案：{loadedPreset?.name ?? "未命名"}</Text>
          </div>
          <div className="panorama-preset-controls">
            <Text type="secondary">已保存方案</Text>
            <Select
              allowClear
              value={selectedPresetId}
              loading={presetsQuery.isLoading}
              placeholder={presetsQuery.data?.length ? "选择区间方案" : "暂无已保存方案"}
              options={(presetsQuery.data ?? []).map((item) => ({
                value: item.id,
                label: `${item.name} · ${item.start_date} → ${item.end_date} · ${item.instruments.length}只`,
              }))}
              onChange={(value) => setSelectedPresetId(value ? String(value) : undefined)}
            />
            <Button icon={<FolderOpen size={15} />} disabled={!selectedPreset} onClick={() => loadPreset(selectedPreset)}>加载</Button>
            <Popconfirm
              title="删除区间方案"
              description={selectedPreset ? `确定删除“${selectedPreset.name}”？` : ""}
              okText="删除"
              onConfirm={() => selectedPreset && deletePresetMutation.mutate(selectedPreset.id)}
            >
              <Button danger icon={<Trash2 size={15} />} disabled={!selectedPreset || deletePresetMutation.isPending}>删除</Button>
            </Popconfirm>
          </div>
          {presetsQuery.error && <Text type="danger">区间方案读取失败：{(presetsQuery.error as Error).message}</Text>}
        </div>
        <div className="panorama-toolbar-main">
          <div className="panorama-search-box">
            <Input
              value={searchValue}
              prefix={<Search size={15} />}
              placeholder="输入指数、股票名称或代码"
              allowClear
              onFocus={() => setSearchOpen(true)}
              onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setSearchValue(event.target.value);
                setSearchOpen(true);
              }}
              onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
                if (event.key === "Enter" && suggestions[0]) addInstrument(suggestions[0]);
                if (event.key === "Escape") setSearchOpen(false);
              }}
            />
            {searchOpen && (
              <div className="panorama-search-results">
                {stockSearch.isFetching && normalizedSearch && <div className="panorama-search-loading"><Spin /> 搜索中…</div>}
                {suggestions.map((item) => (
                  <button key={item.code} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => addInstrument(item)}>
                    <span><strong>{item.name}</strong><small>{item.code}</small></span>
                    <Tag color={item.type === "index" ? "blue" : "default"}>{item.type === "index" ? "指数" : "个股"}</Tag>
                  </button>
                ))}
                {!stockSearch.isFetching && suggestions.length === 0 && <Empty description="没有可添加的匹配项" />}
              </div>
            )}
          </div>
          <Button
            type="primary"
            icon={<Plus size={15} />}
            disabled={!suggestions[0]}
            onClick={() => suggestions[0] && addInstrument(suggestions[0])}
          >添加</Button>
          <Text type="secondary">已添加 {instruments.length}/{MAX_INSTRUMENTS}</Text>
          <Text type={configQuery.error || databaseSaveError ? "danger" : "secondary"}>
            {configQuery.isLoading
              ? "正在读取数据库配置…"
              : configQuery.error || databaseSaveError
                ? `数据库同步失败：${databaseSaveError || (configQuery.error as Error).message}`
                : "已保存到数据库"}
          </Text>
        </div>
        <div className="panorama-quick-indices">
          <Text type="secondary">常用指数</Text>
          {INDEX_OPTIONS.slice(0, 5).map((item) => (
            <button key={item.code} type="button" disabled={existingCodes.has(item.code)} onClick={() => addInstrument(item)}>
              {item.name}
            </button>
          ))}
        </div>
        <div className="panorama-view-controls">
          <Text type="secondary">展示方式</Text>
          <Segmented
            value={viewMode}
            options={[
              { label: "详细", value: "detail" },
              { label: "网格", value: "grid" },
              { label: "涨幅叠加", value: "overlay" },
            ]}
            onChange={(value) => setViewMode(value as PanoramaViewMode)}
          />
          {viewMode === "grid" && (
            <>
              <Text type="secondary">每行</Text>
              <Segmented
                value={gridColumns}
                options={[
                  { label: "2只", value: 2 },
                  { label: "3只", value: 3 },
                ]}
                onChange={(value) => setGridColumns(Number(value) === 3 ? 3 : 2)}
              />
              <Text type="secondary">网格模式仅显示K线与均线</Text>
            </>
          )}
          {viewMode === "overlay" && (
            <>
              <Text type="secondary">图表高度</Text>
              <Segmented
                value={overlayHeight}
                options={[
                  { label: "标准", value: 720 },
                  { label: "加高", value: 1000 },
                  { label: "超高", value: 1400 },
                  { label: "极高", value: 1800 },
                ]}
                onChange={(value) => {
                  const height = Number(value);
                  setOverlayHeight(
                    height === 720 || height === 1400 || height === 1800 ? height : 1000
                  );
                }}
              />
              <Text type="secondary">纵轴范围</Text>
              <Segmented
                value={overlayYAxisMode}
                options={[
                  { label: "聚焦主体", value: "focus" },
                  { label: "完整范围", value: "auto" },
                ]}
                onChange={(value) => setOverlayYAxisMode(value as OverlayYAxisMode)}
              />
              <Text type="secondary">
                {overlayYAxisMode === "focus"
                  ? `当前聚焦 ${overlayFocusBounds.min}% ～ ${overlayFocusBounds.max}%，极端值可切换完整范围查看`
                  : `右侧滑块可继续缩放纵轴 · 展示前 ${MAX_OVERLAY_INSTRUMENTS} 只`}
              </Text>
            </>
          )}
        </div>
      </Card>

      {calendarQuery.isLoading && (
        <Card className="panorama-empty"><div className="panorama-chart-state"><Spin size="large" /><Text type="secondary">正在建立统一交易日历…</Text></div></Card>
      )}
      {calendarQuery.error && (
        <Alert type="error" message="统一交易日历读取失败" description={(calendarQuery.error as Error).message} />
      )}
      {viewMode === "overlay" ? (
        <div className="panorama-overlay-wrap">
          <Card
            className="panorama-overlay-card"
            title="区间涨幅叠加"
            extra={<Text type="secondary">首日归一化为 0% · 悬停查看同日强弱排名</Text>}
          >
            {instruments.length > MAX_OVERLAY_INSTRUMENTS && (
              <Alert
                type="info"
                message={`当前共有 ${instruments.length} 只证券，叠加图展示排序靠前的 ${MAX_OVERLAY_INSTRUMENTS} 只`}
              />
            )}
            {overlayLoading && <div className="panorama-overlay-state" style={{ height: overlayHeight }}><Spin size="large" /><Text type="secondary">正在归一化区间走势…</Text></div>}
            {overlayError && <Alert type="error" message="叠加走势读取失败" description={overlayError.message} />}
            {!overlayLoading && !overlayError && overlaySeries.length > 0 && (
              <ReactECharts option={overlayOption} notMerge lazyUpdate style={{ height: overlayHeight, width: "100%" }} />
            )}
            {!overlayLoading && !overlayError && overlaySeries.length === 0 && (
              <Empty description="当前区间没有可用于比较的行情" />
            )}
          </Card>
        </div>
      ) : (
        <div className={`panorama-chart-list${viewMode === "grid" ? ` is-grid is-grid-${gridColumns}` : ""}`}>
          {timeDomain.length > 0 && instruments.map((instrument, index) => (
            <LazyPanoramaChartSlot key={instrument.code} compact={viewMode === "grid"}>
              <PanoramaChartRow
                instrument={instrument}
                index={index}
                timeDomain={timeDomain}
                syncDate={syncDate}
                syncVisibleRange={syncVisibleRange}
                activeRange={activeRange}
                onHoverDate={handleHoverDate}
                onVisibleRangeChange={handleVisibleRangeChange}
                onRangeSelect={setRangeMenu}
                onRemove={removeInstrument}
                isDragging={dragIndex === index}
                isDropTarget={dragIndex != null && dragIndex !== index && dragOverIndex === index}
                onDragStart={(sourceIndex) => {
                  setDragIndex(sourceIndex);
                  setDragOverIndex(sourceIndex);
                }}
                onDragEnter={setDragOverIndex}
                onDrop={dropInstrument}
                onDragEnd={finishDrag}
                compact={viewMode === "grid"}
              />
            </LazyPanoramaChartSlot>
          ))}
          {timeDomain.length > 0 && instruments.length === 0 && (
            <Card className="panorama-empty">
              <Empty description="请在上方搜索并添加指数或个股" />
            </Card>
          )}
        </div>
      )}

      {rangeMenu && (
        <div
          className="panorama-range-menu"
          style={{
            left: Math.max(12, Math.min(rangeMenu.clientX, window.innerWidth - 250)),
            top: Math.max(72, Math.min(rangeMenu.clientY + 10, window.innerHeight - 260)),
          }}
        >
          <div className="panorama-range-menu-head">
            <strong>已选择区间</strong>
            <span>{rangeMenu.from} → {rangeMenu.to}</span>
          </div>
          <button
            type="button"
            onClick={() => navigate(`/sentiment/interval-gains?start=${rangeMenu.from}&end=${rangeMenu.to}`)}
          >
            <TrendingUp size={16} />
            <span><strong>区间涨幅</strong><small>查看全市场涨幅排行榜</small></span>
          </button>
          <button
            type="button"
            onClick={() => applyRange({ start: rangeMenu.from, end: rangeMenu.to })}
          >
            <CalendarRange size={16} />
            <span><strong>应用到全景图</strong><small>按所选日期重载全部K线</small></span>
          </button>
          <button
            type="button"
            onClick={() => openSaveAsDialog({ start: rangeMenu.from, end: rangeMenu.to })}
          >
            <Plus size={16} />
            <span><strong>另存为区间方案</strong><small>保存当前 {instruments.length} 只证券及其顺序</small></span>
          </button>
        </div>
      )}

      <Modal
        open={!!saveRange}
        title="另存为区间方案"
        okText="创建方案"
        confirmLoading={savePresetMutation.isPending}
        okButtonProps={{ disabled: !presetName.trim() }}
        onCancel={() => {
          if (!savePresetMutation.isPending) setSaveRange(null);
        }}
        onOk={submitPreset}
      >
        <div className="panorama-save-dialog">
          <label>
            <Text type="secondary">方案名称</Text>
            <Input
              autoFocus
              maxLength={80}
              value={presetName}
              placeholder="例如：2026年8月机器人主升周期"
              onChange={(event: ChangeEvent<HTMLInputElement>) => setPresetName(event.target.value)}
              onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
                if (event.key === "Enter" && presetName.trim()) submitPreset();
              }}
            />
          </label>
          <div className="panorama-save-summary">
            <span><strong>日期区间</strong>{saveRange?.start} → {saveRange?.end}</span>
            <span><strong>证券列表</strong>{instruments.length} 只，按当前顺序保存</span>
          </div>
          <div className="panorama-save-instruments">
            {instruments.map((item, index) => (
              <Tag key={item.code}>{index + 1}. {item.name} {item.code}</Tag>
            ))}
          </div>
        </div>
      </Modal>
    </div>
  );
}
