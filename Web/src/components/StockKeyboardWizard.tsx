import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { searchStocks, type StockSearchItem } from "@/api/stocks";

interface Props {
  /** 选中股票后回调（代码已大写） */
  onSelect: (code: string, item: StockSearchItem) => void;
  /** 是否启用全局键盘监听 */
  enabled?: boolean;
}

const KEY_RE = /^[a-zA-Z0-9]$/;

function isEditableTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return Boolean(el.closest(".ant-select, .ant-picker, [contenteditable='true']"));
}

export default function StockKeyboardWizard({ onSelect, enabled = true }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const searchQ = useQuery({
    queryKey: ["stock-search", query],
    queryFn: () => searchStocks(query, 15),
    enabled: open && query.length > 0,
    staleTime: 30_000,
  });

  const results = searchQ.data ?? [];

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIdx(0);
  }, []);

  const pick = useCallback(
    (item: StockSearchItem) => {
      onSelect(item.code.toUpperCase(), item);
      close();
    },
    [close, onSelect]
  );

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      if (open) {
        const inPanel = panelRef.current?.contains(e.target as Node);
        const navKey = ["Enter", "Escape", "ArrowUp", "ArrowDown"].includes(e.key);
        if (inPanel && !navKey && e.key !== "Backspace") {
          return;
        }

        if (e.key === "Escape") {
          e.preventDefault();
          close();
          return;
        }
        if (e.key === "Enter") {
          e.preventDefault();
          const item = results[activeIdx];
          if (item) pick(item);
          return;
        }
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setActiveIdx((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          setActiveIdx((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === "Backspace") {
          e.preventDefault();
          setQuery((q) => q.slice(0, -1));
          setActiveIdx(0);
          return;
        }
        if (KEY_RE.test(e.key)) {
          e.preventDefault();
          setQuery((q) => (q + e.key).slice(0, 32));
          setActiveIdx(0);
        }
        return;
      }

      if (isEditableTarget(e.target)) return;
      if (!KEY_RE.test(e.key)) return;

      e.preventDefault();
      setOpen(true);
      setQuery(e.key);
      setActiveIdx(0);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIdx, close, enabled, open, pick, results]);

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (activeIdx >= results.length) {
      setActiveIdx(Math.max(results.length - 1, 0));
    }
  }, [activeIdx, results.length]);

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      style={{
        position: "fixed",
        top: 72,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1100,
        width: 420,
        background: "#fff",
        border: "1px solid #d9d9d9",
        borderRadius: 8,
        boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
        overflow: "hidden",
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div
        style={{
          padding: "8px 12px",
          background: "#fafafa",
          borderBottom: "1px solid #f0f0f0",
          fontSize: 13,
          fontWeight: 600,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span>键盘精灵</span>
        <span style={{ fontSize: 11, color: "#999", fontWeight: 400 }}>
          ↑↓ 选择 · Enter 确认 · Esc 关闭
        </span>
      </div>

      <div style={{ padding: "8px 12px", borderBottom: "1px solid #f0f0f0" }}>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value.slice(0, 32));
            setActiveIdx(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              const item = results[activeIdx];
              if (item) pick(item);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setActiveIdx((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActiveIdx((i) => Math.max(i - 1, 0));
            }
          }}
          placeholder="输入代码 / 名称 / 拼音首字母"
          style={{
            width: "100%",
            border: "none",
            outline: "none",
            fontSize: 15,
            padding: "4px 0",
          }}
        />
      </div>

      <div style={{ maxHeight: 320, overflowY: "auto" }}>
        {query.length === 0 && (
          <div style={{ padding: 16, color: "#999", textAlign: "center", fontSize: 13 }}>
            继续输入以搜索股票…
          </div>
        )}
        {query.length > 0 && searchQ.isLoading && (
          <div style={{ padding: 16, color: "#999", textAlign: "center", fontSize: 13 }}>
            搜索中…
          </div>
        )}
        {query.length > 0 && !searchQ.isLoading && results.length === 0 && (
          <div style={{ padding: 16, color: "#999", textAlign: "center", fontSize: 13 }}>
            未找到匹配股票
          </div>
        )}
        {results.map((item, idx) => (
          <div
            key={item.code}
            role="button"
            tabIndex={0}
            onMouseEnter={() => setActiveIdx(idx)}
            onClick={() => pick(item)}
            style={{
              display: "grid",
              gridTemplateColumns: "88px 1fr 52px",
              gap: 8,
              padding: "8px 12px",
              cursor: "pointer",
              background: idx === activeIdx ? "#e6f4ff" : "transparent",
              borderBottom: "1px solid #f5f5f5",
              fontSize: 13,
              alignItems: "center",
            }}
          >
            <span style={{ fontFamily: "monospace", color: "#1677ff" }}>
              {item.code.replace(/^SH|^SZ/i, "")}
            </span>
            <span>{item.name}</span>
            <span style={{ color: "#1677ff", textAlign: "right" }}>{item.market}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
