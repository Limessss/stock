import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, CalendarDays, Plus, Search, Trash2, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getKline } from "@/api/kline";
import {
  getPanoramaConfig,
  savePanoramaConfig,
  type PanoramaInstrumentRecord,
} from "@/api/panorama";
import { searchStocks, type StockSearchItem } from "@/api/stocks";
import KlineChart, {
  type KlineSelectedRange,
  type KlineVisibleRange,
} from "@/components/KlineChart";
import { Alert, Button, Card, Empty, Input, Spin, Tag, Typography, message } from "@/components/ui";

const { Title, Text } = Typography;
const STORAGE_KEY = "stockmodel.leader-cycle-panorama.v1";
const YEAR_BARS = 252;
const MAX_INSTRUMENTS = 16;

type PanoramaInstrument = PanoramaInstrumentRecord;

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

interface ChartRowProps {
  instrument: PanoramaInstrument;
  index: number;
  count: number;
  timeDomain: string[];
  syncDate: string | null;
  syncVisibleRange: KlineVisibleRange | null;
  onHoverDate: (date: string | null) => void;
  onVisibleRangeChange: (range: KlineVisibleRange) => void;
  onRangeSelect: (range: KlineSelectedRange) => void;
  onMove: (index: number, offset: number) => void;
  onRemove: (code: string) => void;
}

function PanoramaChartRow({
  instrument,
  index,
  count,
  timeDomain,
  syncDate,
  syncVisibleRange,
  onHoverDate,
  onVisibleRangeChange,
  onRangeSelect,
  onMove,
  onRemove,
}: ChartRowProps) {
  const query = useQuery({
    queryKey: ["leader-cycle-panorama", instrument.code, YEAR_BARS],
    queryFn: () => getKline(instrument.code, { lastN: YEAR_BARS }),
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

  return (
    <Card className="panorama-chart-card">
      <div className="panorama-chart-head">
        <div className="panorama-instrument-title">
          <strong>{displayName}</strong>
          <Text code>{instrument.code}</Text>
          <Tag color={instrument.type === "index" ? "blue" : "default"}>
            {instrument.type === "index" ? "指数" : "个股"}
          </Tag>
          {domainStart && domainEnd && <Text type="secondary">{domainStart} — {domainEnd}</Text>}
          {periodGain != null && (
            <strong className={periodGain >= 0 ? "panorama-gain-positive" : "panorama-gain-negative"}>
              {periodGain > 0 ? "+" : ""}{periodGain.toFixed(2)}%
            </strong>
          )}
        </div>
        <div className="panorama-row-actions">
          <Button
            aria-label="上移"
            title="上移"
            icon={<ArrowUp size={15} />}
            disabled={index === 0}
            onClick={() => onMove(index, -1)}
          />
          <Button
            aria-label="下移"
            title="下移"
            icon={<ArrowDown size={15} />}
            disabled={index === count - 1}
            onClick={() => onMove(index, 1)}
          />
          <Button
            danger
            aria-label="删除"
            title="删除"
            icon={<Trash2 size={15} />}
            onClick={() => onRemove(instrument.code)}
          />
        </div>
      </div>

      {query.isLoading && <div className="panorama-chart-state"><Spin size="large" /><Text type="secondary">正在读取本地日K…</Text></div>}
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
          height={340}
          visibleBars={YEAR_BARS}
          focusDate={domainEnd || last?.time}
          timeDomain={timeDomain}
          syncDate={syncDate}
          onHoverDate={onHoverDate}
          syncVisibleRange={syncVisibleRange}
          onVisibleRangeChange={onVisibleRangeChange}
          onRangeSelect={onRangeSelect}
        />
      )}
      {query.data && candles.length === 0 && <Empty description="本地没有该证券的日K数据" />}
    </Card>
  );
}

export default function LeaderCyclePanoramaPage() {
  const navigate = useNavigate();
  const [instruments, setInstruments] = useState<PanoramaInstrument[]>(loadSavedInstruments);
  const [searchValue, setSearchValue] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [syncDate, setSyncDate] = useState<string | null>(null);
  const [syncVisibleRange, setSyncVisibleRange] = useState<KlineVisibleRange | null>(null);
  const [rangeMenu, setRangeMenu] = useState<KlineSelectedRange | null>(null);
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
    queryKey: ["leader-cycle-panorama", "SH000001", YEAR_BARS],
    queryFn: () => getKline("SH000001", { lastN: YEAR_BARS }),
    staleTime: 10 * 60_000,
  });
  const timeDomain = useMemo(
    () => (calendarQuery.data?.candles ?? []).map((bar) => bar.time),
    [calendarQuery.data?.candles]
  );

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

  const moveInstrument = useCallback((index: number, offset: number) => {
    setInstruments((current) => {
      const target = index + offset;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }, []);

  const removeInstrument = useCallback((code: string) => {
    setInstruments((current) => current.filter((item) => item.code !== code));
  }, []);

  const handleHoverDate = useCallback((date: string | null) => setSyncDate(date), []);
  const handleVisibleRangeChange = useCallback((range: KlineVisibleRange) => {
    setSyncVisibleRange((current) => (
      current?.from === range.from && current.to === range.to ? current : range
    ));
  }, []);

  return (
    <div className="sentiment-page leader-panorama-page">
      <div className="sentiment-page-header panorama-page-header">
        <div>
          <Title level={3} style={{ margin: 0 }}>龙头周期全景图</Title>
          <Text type="secondary">日期与缩放全图联动 · 按住左键拖拽选择区间 · 松开查看分析菜单</Text>
        </div>
        <div className={`panorama-sync-date${syncDate ? " is-active" : ""}`}>
          <CalendarDays size={16} />
          <span>{syncDate ? `联动日期 ${syncDate}` : "移动鼠标查看联动日期"}</span>
        </div>
        <div className={`panorama-sync-date panorama-sync-range${syncVisibleRange ? " is-active" : ""}`}>
          <span>{syncVisibleRange ? `联动区间 ${syncVisibleRange.from} — ${syncVisibleRange.to}` : "缩放或拖动任一K线可同步视窗"}</span>
        </div>
      </div>

      <Card className="panorama-toolbar">
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
      </Card>

      {calendarQuery.isLoading && (
        <Card className="panorama-empty"><div className="panorama-chart-state"><Spin size="large" /><Text type="secondary">正在建立统一交易日历…</Text></div></Card>
      )}
      {calendarQuery.error && (
        <Alert type="error" message="统一交易日历读取失败" description={(calendarQuery.error as Error).message} />
      )}
      <div className="panorama-chart-list">
        {timeDomain.length > 0 && instruments.map((instrument, index) => (
          <PanoramaChartRow
            key={instrument.code}
            instrument={instrument}
            index={index}
            count={instruments.length}
            timeDomain={timeDomain}
            syncDate={syncDate}
            syncVisibleRange={syncVisibleRange}
            onHoverDate={handleHoverDate}
            onVisibleRangeChange={handleVisibleRangeChange}
            onRangeSelect={setRangeMenu}
            onMove={moveInstrument}
            onRemove={removeInstrument}
          />
        ))}
        {timeDomain.length > 0 && instruments.length === 0 && (
          <Card className="panorama-empty">
            <Empty description="请在上方搜索并添加指数或个股" />
          </Card>
        )}
      </div>

      {rangeMenu && (
        <div
          className="panorama-range-menu"
          style={{
            left: Math.max(12, Math.min(rangeMenu.clientX, window.innerWidth - 250)),
            top: Math.max(72, Math.min(rangeMenu.clientY + 10, window.innerHeight - 120)),
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
        </div>
      )}
    </div>
  );
}
