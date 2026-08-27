import { useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";

import { searchStocks, type StockSearchItem } from "@/api/stocks";

interface Props {
  open: boolean;
  query: string;
  activeIdx: number;
  onQueryChange: (q: string) => void;
  onActiveIdxChange: (idx: number) => void;
  onSelect: (item: StockSearchItem) => void;
  onClose: () => void;
}

export default function StockMentionMenu({
  open,
  query,
  activeIdx,
  onQueryChange,
  onActiveIdxChange,
  onSelect,
  onClose,
}: Props) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  const searchQ = useQuery({
    queryKey: ["stock-mention", query],
    queryFn: () => searchStocks(query, 12),
    enabled: open && query.length > 0,
    staleTime: 30_000,
  });

  const results = searchQ.data ?? [];

  useEffect(() => {
    if (activeIdx >= results.length) {
      onActiveIdxChange(Math.max(results.length - 1, 0));
    }
  }, [activeIdx, onActiveIdxChange, results.length]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const item = results[activeIdx];
        if (item) onSelect(item);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        onActiveIdxChange(Math.min(activeIdx + 1, Math.max(results.length - 1, 0)));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        onActiveIdxChange(Math.max(activeIdx - 1, 0));
        return;
      }
      if (e.key === "Backspace") {
        e.preventDefault();
        if (query.length <= 1) {
          onClose();
        } else {
          onQueryChange(query.slice(0, -1));
          onActiveIdxChange(0);
        }
        return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        onQueryChange((query + e.key).slice(0, 32));
        onActiveIdxChange(0);
      }
    },
    [activeIdx, onActiveIdxChange, onClose, onQueryChange, onSelect, open, query, results]
  );

  useEffect(() => {
    if (!open) return;
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [handleKeyDown, open]);

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      className="stock-mention-menu"
      onMouseDown={(e) => e.preventDefault()}
    >
      <div className="stock-mention-menu-header">
        <span>插入股票</span>
        <span className="stock-mention-menu-hint">↑↓ 选择 · Enter 确认 · Esc 取消</span>
      </div>
      <div className="stock-mention-menu-query">#{query || "…"}</div>
      <div className="stock-mention-menu-list">
        {query.length === 0 && (
          <div className="stock-mention-menu-empty">继续输入代码 / 名称 / 拼音…</div>
        )}
        {query.length > 0 && searchQ.isLoading && (
          <div className="stock-mention-menu-empty">搜索中…</div>
        )}
        {query.length > 0 && !searchQ.isLoading && results.length === 0 && (
          <div className="stock-mention-menu-empty">未找到匹配股票</div>
        )}
        {results.map((item, idx) => (
          <div
            key={item.code}
            role="button"
            tabIndex={0}
            className={`stock-mention-menu-item${idx === activeIdx ? " active" : ""}`}
            onMouseEnter={() => onActiveIdxChange(idx)}
            onClick={() => onSelect(item)}
          >
            <span className="code">{item.code.replace(/^SH|^SZ/i, "")}</span>
            <span className="name">{item.name}</span>
            <span className="market">{item.market}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
