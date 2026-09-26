import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowDownWideNarrow, ArrowRight, Bot, Check, ChevronLeft, ChevronRight, Copy, FileText, Plug, RefreshCw, Search } from "lucide-react";

import { getAiReviewOverview, getReviewInstructions, listAiReviews, type AiReviewSummary, type ReviewFilters } from "@/api/aiReviews";
import { formatBeijingTime, nowBeijing, parseBeijingDate } from "@/lib/dayjsSetup";
import "./aiReviews.css";

export async function copyReviewText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return; } catch { /* 非安全上下文用传统复制 */ }
  }
  const previousFocus = document.activeElement as HTMLElement | null;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.cssText = "position:fixed;left:-9999px;top:0;";
  document.body.appendChild(textarea);
  try {
    textarea.select();
    if (!document.execCommand("copy")) throw new Error("复制失败，请展开指令后手动复制。");
  } finally {
    textarea.remove();
    previousFocus?.focus();
  }
}

export function AgentBadge({ name }: { name: string }) {
  const hue = [...name].reduce((value, char) => value + char.charCodeAt(0), 0) % 360;
  return <span className="air-agent"><i style={{ background: `hsl(${hue} 65% 58%)` }} /><Bot size={13} />{name}</span>;
}

function ReportCard({ report, search }: { report: AiReviewSummary; search: string }) {
  return <Link className="air-report-card" to={`/ai-reviews/${report.id}${search}`}>
    <div className="air-card-meta"><AgentBadge name={report.agent_name} />{report.model && <span className="air-model">{report.model}</span>}<ArrowRight size={16} className="air-card-arrow" /></div>
    <h3>{report.title}</h3>
    <p className="air-card-summary">{report.summary || "打开报告，查看完整复盘内容。"}</p>
    {report.tags.length > 0 && <div className="air-tags">{report.tags.slice(0, 6).map(tag => <span key={tag}>{tag}</span>)}{report.tags.length > 6 && <span>+{report.tags.length - 6}</span>}</div>}
    <footer><span>{formatBeijingTime(report.created_at, "MM-DD HH:mm:ss")} 提交 · 北京时间</span><span>阅读报告 <ChevronRight size={13} /></span></footer>
  </Link>;
}

export default function AiReviewsPage() {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [selectedDate, setSelectedDate] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "copying" | "done" | "error">("idle");
  const [showInstructions, setShowInstructions] = useState(false);
  const [showConnection, setShowConnection] = useState(false);
  const [client, setClient] = useState<"codex" | "claude">("codex");
  const [configCopied, setConfigCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const overview = useQuery({ queryKey: ["ai-reviews", "overview"], queryFn: getAiReviewOverview, refetchInterval: 15_000 });
  const tradeDate = selectedDate || overview.data?.latest_data_date || nowBeijing().format("YYYY-MM-DD");
  const instructions = useQuery({ queryKey: ["ai-reviews", "instructions", tradeDate], queryFn: () => getReviewInstructions(tradeDate), enabled: !overview.isPending });
  const filters: ReviewFilters = {
    start_date: params.get("start") || undefined, end_date: params.get("end") || undefined,
    agent_name: params.get("agent") || undefined, q: params.get("q") || undefined,
    order: params.get("order") === "asc" ? "asc" : "desc",
    page: Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1), page_size: 20,
  };
  const badRange = !!(filters.start_date && filters.end_date && filters.start_date > filters.end_date);
  const reports = useQuery({ queryKey: ["ai-reviews", "list", filters], queryFn: () => listAiReviews(filters), refetchInterval: 15_000, enabled: !badRange });
  const groups = useMemo(() => {
    const grouped = new Map<string, AiReviewSummary[]>();
    for (const report of reports.data?.items || []) {
      grouped.set(report.trade_date, [...(grouped.get(report.trade_date) || []), report]);
    }
    return [...grouped.entries()];
  }, [reports.data]);
  const hasFilters = !!(filters.q || filters.agent_name || filters.start_date || filters.end_date);
  const pages = Math.max(1, Math.ceil((reports.data?.total || 0) / filters.page_size));
  const search = params.toString() ? `?${params.toString()}` : "";

  function updateFilter(key: string, value: string) {
    setParams(current => {
      const next = new URLSearchParams(current);
      value ? next.set(key, value) : next.delete(key);
      if (key !== "page") next.delete("page");
      return next;
    }, { replace: true });
  }

  async function copyInstructions() {
    if (copyState === "copying") return;
    setSelectedDate(tradeDate);
    setCopyState("copying");
    setCopyError("");
    // 每次复制都重新请求源文件；读取失败时不能复制查询缓存中的旧版本。
    try {
      const result = await instructions.refetch({ throwOnError: true });
      if (!result.data || result.data.trade_date !== tradeDate) throw new Error("复盘日期不一致，请重新复制。");
      await copyReviewText(result.data.prompt);
      setCopyState("done");
    }
    catch (error) { setCopyState("error"); setCopyError((error as Error).message); setShowInstructions(true); }
  }

  return <div className="air-page">
    <header className="air-heading">
      <div><div className="air-eyebrow"><Bot size={15} /> AGENT RESEARCH</div><h1>AI复盘</h1><p>把复盘交给你的 Agent，让每天的判断留下记录。</p></div>
      <button className="air-button" onClick={() => setShowConnection(value => !value)} aria-expanded={showConnection}><Plug size={16} />MCP 接入</button>
    </header>

    <section className="air-compose" aria-label="创建复盘指令">
      <div className="air-compose-copy"><h2>一条指令，开始今日复盘</h2><p>每次复制都会读取《完整情绪周期操作手册》的最新内容，交给 Agent 复盘并回传报告。</p><div className="air-workflow"><span><b>1</b>选择日期</span><i /><span><b>2</b>复制指令给 Agent</span><i /><span><b>3</b>报告归档到时间轴</span></div></div>
      <div className="air-compose-actions"><label htmlFor="review-date">复盘日期</label><div><input id="review-date" type="date" value={tradeDate} disabled={copyState === "copying"} max={nowBeijing().format("YYYY-MM-DD")} onChange={event => { setSelectedDate(event.target.value); setCopyState("idle"); setCopyError(""); }} /><button className="air-button air-button-primary" disabled={overview.isPending || instructions.isFetching || copyState === "copying"} onClick={copyInstructions}>{copyState === "done" ? <Check size={16} /> : <Copy size={16} />}{copyState === "copying" ? "正在读取最新手册…" : copyState === "done" ? "已复制 · 粘贴给 Agent" : "复制AI复盘指令"}</button></div><button className="air-text-button" onClick={() => { if (!showInstructions) void instructions.refetch(); setShowInstructions(value => !value); }} aria-expanded={showInstructions}>{showInstructions ? "收起指令" : "预览完整指令"}</button></div>
    </section>
    <div aria-live="polite">{copyState === "done" && <p className="air-notice">已复制 {tradeDate} 的复盘指令。粘贴给 Agent 后，本页会自动检查新报告。</p>}{copyError && <p className="air-error">{copyError}</p>}{instructions.isError && <p className="air-error">指令加载失败：{instructions.error.message}<button className="air-text-button" onClick={() => void instructions.refetch()}>重试</button></p>}</div>
    {showInstructions && <section className="air-panel"><div className="air-panel-heading"><h2>{tradeDate} · 复盘指令</h2><span>包含最新手册全文、分析要求和提交格式</span></div><textarea className="air-prompt" aria-label="完整复盘指令" value={instructions.isFetching ? "正在读取最新手册…" : instructions.isError ? "指令加载失败，请检查上方提示后重试。" : instructions.data?.prompt || "正在加载…"} readOnly onFocus={event => event.target.select()} /></section>}
    {showConnection && <section className="air-panel air-connection">
      <div className="air-panel-heading"><h2><Plug size={17} />连接你的 Agent</h2><span>本机 stdio · 首次使用时配置</span></div>
      <p>保持项目后端运行，将下面配置合并到客户端配置文件，再重新加载 MCP。复制的复盘指令也已包含这些信息。</p>
      <div className="air-config-toolbar"><div role="tablist" aria-label="MCP 客户端">{(["codex", "claude"] as const).map(value => <button key={value} role="tab" aria-selected={client === value} className={client === value ? "is-active" : ""} onClick={() => { setClient(value); setConfigCopied(false); }}>{value === "codex" ? "Codex" : "Claude Code"}</button>)}</div><button className="air-button" disabled={!instructions.data} onClick={async () => { try { await copyReviewText(client === "codex" ? instructions.data!.connection.codex_config : instructions.data!.connection.claude_config); setConfigCopied(true); setCopyError(""); } catch (error) { setCopyError((error as Error).message); } }}><Copy size={14} />{configCopied ? "已复制配置" : "复制配置"}</button></div>
      <p className="air-config-path">{client === "codex" ? "~/.codex/config.toml" : "项目根目录 .mcp.json"}</p>
      <pre>{client === "codex" ? instructions.data?.connection.codex_config : instructions.data?.connection.claude_config}</pre>
      <p className="air-muted">此配置用于项目所在电脑上的 Agent。首次连接后，日常只需复制复盘指令。报告由外部 Agent 生成，模型由该 Agent 的配置决定。</p>
    </section>}

    <section className="air-archive" aria-label="复盘时间轴">
      <div className="air-archive-heading"><div><h2>复盘时间轴</h2><span>{overview.data ? `${overview.data.report_count} 份报告 · ${overview.data.agent_count} 个 Agent` : "报告归档"}</span></div><div className="air-archive-status"><span>本地情绪数据至 {overview.data?.latest_data_date || "—"}</span><button className="air-button" onClick={() => void queryClient.invalidateQueries({ queryKey: ["ai-reviews"] })} disabled={reports.isFetching} aria-label="刷新复盘报告"><RefreshCw size={14} className={reports.isFetching ? "air-spinning" : ""} />刷新</button></div></div>
      {overview.isError && <p className="air-error">归档统计加载失败：{overview.error.message}</p>}
      <div className="air-filters">
        <form className="air-search" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); updateFilter("q", String(form.get("q") || "")); }}><Search size={16} /><input key={filters.q || ""} name="q" aria-label="搜索复盘报告" placeholder="搜索标题或报告内容" maxLength={200} defaultValue={filters.q || ""} /><button type="submit">搜索</button></form>
        <select aria-label="筛选 Agent" value={filters.agent_name || ""} onChange={event => updateFilter("agent", event.target.value)}><option value="">全部 Agent</option>{overview.data?.agents.map(agent => <option key={agent.name} value={agent.name}>{agent.name}（{agent.count}）</option>)}</select>
        <div className="air-date-range"><input aria-label="开始日期" type="date" value={filters.start_date || ""} onChange={event => updateFilter("start", event.target.value)} /><span>至</span><input aria-label="结束日期" type="date" value={filters.end_date || ""} onChange={event => updateFilter("end", event.target.value)} /></div>
        <button className="air-button air-sort" onClick={() => updateFilter("order", filters.order === "desc" ? "asc" : "desc")}><ArrowDownWideNarrow size={15} />{filters.order === "desc" ? "最新在前" : "最早在前"}</button>
        {hasFilters && <button className="air-text-button" onClick={() => setParams({})}>清空筛选</button>}
      </div>
      {badRange ? <p className="air-error">开始日期不能晚于结束日期。</p> : reports.isError ? <div className="air-empty" role="alert"><p>报告加载失败：{reports.error.message}</p><button className="air-button" onClick={() => void reports.refetch()}>重新加载</button></div> : reports.isPending ? <div className="air-empty"><RefreshCw size={24} className="air-spinning" /><p>正在读取复盘报告…</p></div> : groups.length === 0 ? <div className="air-empty"><span className="air-empty-icon"><FileText size={28} /></span><h3>{hasFilters ? "没有符合筛选条件的报告" : "从第一份 AI 复盘开始"}</h3><p>{hasFilters ? "调整日期、Agent 或搜索词，查看其他复盘。" : "选好日期，复制上方指令给 Agent。提交成功后，报告会自动出现在这里。"}</p>{hasFilters && <button className="air-button" onClick={() => setParams({})}>清空筛选</button>}{filters.page > 1 && <button className="air-button" onClick={() => updateFilter("page", "1")}>返回第一页</button>}</div> : <div className="air-timeline">{groups.map(([date, items]) => <section className="air-day" key={date}><div className="air-day-label"><time dateTime={date}>{date}</time><span>{parseBeijingDate(date).format("dddd")}</span><i /></div><div className="air-day-reports">{items.map(report => <ReportCard key={report.id} report={report} search={search} />)}</div></section>)}</div>}
      {!badRange && reports.data && reports.data.total > 0 && <footer className="air-pagination"><span>共 {reports.data.total} 份 · 每页 20 份 · 同日按提交时间排序</span><div><button className="air-button" disabled={filters.page <= 1} onClick={() => updateFilter("page", String(filters.page - 1))} aria-label="上一页"><ChevronLeft size={16} /></button><span>{filters.page} / {pages}</span><button className="air-button" disabled={filters.page >= pages} onClick={() => updateFilter("page", String(filters.page + 1))} aria-label="下一页"><ChevronRight size={16} /></button></div></footer>}
    </section>
  </div>;
}
