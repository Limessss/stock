import { searchStocks, type StockSearchItem } from "@/api/stocks";

const MENTION_SPAN_RE =
  /(<span[^>]*class="[^"]*stock-mention[^"]*"[^>]*>[\s\S]*?<\/span>)/gi;
const PLAIN_MENTION_RE = /#([^\s#<>/&]{2,32})/g;

export function buildStockMentionHtml(item: StockSearchItem): string {
  const code = item.code.toUpperCase();
  const name = item.name.replace(/"/g, "&quot;");
  return `<span class="stock-mention" data-code="${code}" data-name="${name}">#${item.name}</span>`;
}

/** 编辑器内只存纯文本，把已保存的 stock-mention 标签还原为 #名称 */
export function htmlToPlainForEditor(html: string): string {
  if (!html) return "<p><br></p>";
  let out = html.replace(
    /<span[^>]*class="[^"]*stock-mention[^"]*"[^>]*>[\s\S]*?<\/span>/gi,
    (span) => {
      const nameMatch = span.match(/data-name="([^"]*)"/i);
      const textMatch = span.match(/>(#[^<]*)</);
      if (nameMatch) {
        return `#${nameMatch[1].replace(/&quot;/g, '"')} `;
      }
      if (textMatch) return `${textMatch[1]} `;
      return "";
    }
  );
  return out;
}

function pickBestMatch(query: string, items: StockSearchItem[]): StockSearchItem | null {
  if (!items.length) return null;
  const q = query.trim();
  const qUpper = q.toUpperCase();
  const exactName = items.find((i) => i.name === q);
  if (exactName) return exactName;
  const exactCode = items.find(
    (i) => i.code.toUpperCase() === qUpper || i.code.toUpperCase().endsWith(qUpper)
  );
  if (exactCode) return exactCode;
  const startsName = items.find((i) => i.name.startsWith(q));
  if (startsName) return startsName;
  return items[0];
}

async function linkifyTextSegment(text: string): Promise<string> {
  if (!text.includes("#")) return text;

  const queries = new Set<string>();
  let m: RegExpExecArray | null;
  const re = new RegExp(PLAIN_MENTION_RE.source, "g");
  while ((m = re.exec(text)) !== null) {
    queries.add(m[1]);
  }
  if (queries.size === 0) return text;

  const resolved = new Map<string, StockSearchItem>();
  await Promise.all(
    [...queries].map(async (q) => {
      const items = await searchStocks(q, 8);
      const best = pickBestMatch(q, items);
      if (best) resolved.set(q, best);
    })
  );

  if (resolved.size === 0) return text;

  return text.replace(new RegExp(PLAIN_MENTION_RE.source, "g"), (full, q: string) => {
    const item = resolved.get(q);
    if (!item) return full;
    return buildStockMentionHtml(item);
  });
}

/** 预览/保存时：将 #股票名 转为可点击标签（勿写回 wangEditor） */
export async function linkifyStockMentions(html: string): Promise<string> {
  if (!html || !html.includes("#")) return html;

  const plain = htmlToPlainForEditor(html);
  const parts = plain.split(MENTION_SPAN_RE);
  if (parts.length === 1) {
    return linkifyTextSegment(plain);
  }

  const out: string[] = [];
  for (const part of parts) {
    if (!part) continue;
    if (/class="[^"]*stock-mention/i.test(part)) {
      out.push(part);
    } else {
      out.push(await linkifyTextSegment(part));
    }
  }
  return out.join("");
}

export function parseLinkedCodesFromHtml(html: string): string[] {
  const fromData = html.match(/data-code="([^"]+)"/gi);
  if (fromData?.length) {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const m of fromData) {
      const code = m.replace(/data-code="/i, "").replace(/"$/, "").toUpperCase();
      if (!seen.has(code)) {
        seen.add(code);
        out.push(code);
      }
    }
    if (out.length) return out;
  }
  return [];
}

/** 保存前从纯文本 #关键词 解析关联代码（供后端 linked_codes） */
export async function resolveLinkedCodesFromPlain(html: string): Promise<string[]> {
  const linked = await linkifyStockMentions(html);
  return parseLinkedCodesFromHtml(linked);
}
