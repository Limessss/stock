import { useMemo } from "react";

import type { StockKlineTarget } from "@/components/StockKlineModal";

export interface NoteStockMention {
  code: string;
  name: string;
}

interface Props {
  text: string;
  mentions?: NoteStockMention[];
  onStockClick: (stock: StockKlineTarget) => void;
}

interface TextPart {
  kind: "text";
  value: string;
}

interface MentionPart {
  kind: "mention";
  label: string;
  code: string;
  name: string;
}

function buildParts(text: string, mentions: NoteStockMention[]): Array<TextPart | MentionPart> {
  if (!text) return [{ kind: "text", value: "（空）" }];
  if (!mentions.length) return [{ kind: "text", value: text }];

  const byName = new Map(mentions.map((m) => [m.name, m]));
  const parts: Array<TextPart | MentionPart> = [];
  const re = /#([^\s#]+)/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ kind: "text", value: text.slice(last, match.index) });
    }
    const label = match[0];
    const key = match[1];
    const hit =
      byName.get(key) ??
      mentions.find(
        (m) =>
          m.code.toUpperCase() === key.toUpperCase() ||
          m.code.toUpperCase().endsWith(key.toUpperCase())
      );
    if (hit) {
      parts.push({ kind: "mention", label, code: hit.code, name: hit.name });
    } else {
      parts.push({ kind: "text", value: label });
    }
    last = match.index + label.length;
  }

  if (last < text.length) {
    parts.push({ kind: "text", value: text.slice(last) });
  }
  return parts.length ? parts : [{ kind: "text", value: text }];
}

export default function NoteExcerpt({ text, mentions = [], onStockClick }: Props) {
  const parts = useMemo(() => buildParts(text, mentions), [mentions, text]);

  return (
    <div className="note-list-excerpt">
      {parts.map((part, idx) =>
        part.kind === "text" ? (
          <span key={idx}>{part.value}</span>
        ) : (
          <span
            key={idx}
            role="button"
            tabIndex={0}
            className="stock-mention"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onStockClick({ code: part.code, name: part.name });
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                onStockClick({ code: part.code, name: part.name });
              }
            }}
          >
            {part.label}
          </span>
        )
      )}
    </div>
  );
}
