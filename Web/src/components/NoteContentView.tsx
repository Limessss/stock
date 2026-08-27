import { useCallback, useEffect, useRef, useState } from "react";
import { Space, Spin, Tag } from "@/components/ui";

import StockKlineModal, { type StockKlineTarget } from "@/components/StockKlineModal";
import {
  linkifyStockMentions,
  parseLinkedCodesFromHtml,
} from "@/lib/stockMention";

interface Props {
  html: string;
  tradeDate?: string | null;
  showStockChips?: boolean;
  onStockClick?: (stock: StockKlineTarget) => void;
}

function readMention(el: HTMLElement): StockKlineTarget | null {
  const code = el.getAttribute("data-code");
  if (!code) return null;
  return {
    code: code.toUpperCase(),
    name: el.getAttribute("data-name") ?? undefined,
  };
}

export default function NoteContentView({
  html,
  tradeDate,
  showStockChips = true,
  onStockClick,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [displayHtml, setDisplayHtml] = useState("");
  const [linkifying, setLinkifying] = useState(true);
  const [linkedCodes, setLinkedCodes] = useState<string[]>([]);
  const [klineOpen, setKlineOpen] = useState(false);
  const [klineStock, setKlineStock] = useState<StockKlineTarget | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLinkifying(true);
    linkifyStockMentions(html).then((linked) => {
      if (cancelled) return;
      setDisplayHtml(linked);
      setLinkedCodes(parseLinkedCodesFromHtml(linked));
      setLinkifying(false);
    });
    return () => {
      cancelled = true;
    };
  }, [html]);

  const openKline = useCallback(
    (stock: StockKlineTarget) => {
      if (onStockClick) {
        onStockClick(stock);
        return;
      }
      setKlineStock({
        ...stock,
        signalDate: tradeDate ?? stock.signalDate,
      });
      setKlineOpen(true);
    },
    [onStockClick, tradeDate]
  );

  const onClick = useCallback(
    (e: React.MouseEvent) => {
      const target = (e.target as HTMLElement).closest(".stock-mention") as HTMLElement | null;
      if (!target || !containerRef.current?.contains(target)) return;
      e.preventDefault();
      const stock = readMention(target);
      if (stock) openKline(stock);
    },
    [openKline]
  );

  if (linkifying) {
    return (
      <div style={{ textAlign: "center", padding: 48 }}>
        <Spin tip="解析股票标签…" />
      </div>
    );
  }

  return (
    <>
      <div
        ref={containerRef}
        className="note-content-view"
        dangerouslySetInnerHTML={{ __html: displayHtml || "<p><br></p>" }}
        onClick={onClick}
      />
      {showStockChips && linkedCodes.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Space wrap size={[8, 8]}>
            <span style={{ color: "#666", fontSize: 13 }}>提及股票：</span>
            {linkedCodes.map((code) => (
              <Tag
                key={code}
                color="blue"
                style={{ cursor: "pointer" }}
                onClick={() => openKline({ code })}
              >
                {code}
              </Tag>
            ))}
          </Space>
        </div>
      )}
      <StockKlineModal
        open={!onStockClick && klineOpen}
        stock={klineStock}
        onClose={() => setKlineOpen(false)}
      />
    </>
  );
}
