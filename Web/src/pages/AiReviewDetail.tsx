import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkCjkFriendly from "remark-cjk-friendly/parseOnly";
import { ArrowLeft, Copy, Download, RefreshCw } from "lucide-react";

import { getAiReview } from "@/api/aiReviews";
import { formatBeijingTime } from "@/lib/dayjsSetup";
import { rehypeReviewAppendix } from "@/lib/reviewAppendix";
import { AgentBadge, copyReviewText } from "./AiReviews";
import "./aiReviews.css";

export default function AiReviewDetailPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const report = useQuery({ queryKey: ["ai-reviews", "detail", id], queryFn: () => getAiReview(id), enabled: !!id });
  const [copyMessage, setCopyMessage] = useState("");
  const data = report.data;

  function downloadMarkdown() {
    if (!data) return;
    const header = `# ${data.title}\n\n复盘日期：${data.trade_date}\n\nAgent：${data.agent_name}${data.model ? ` · ${data.model}` : ""}\n\n提交时间：${formatBeijingTime(data.created_at)}（北京时间）\n\n---\n\n`;
    const blob = new Blob([header, data.content_markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${data.trade_date}-${data.agent_name}-${data.id.slice(0, 8)}.md`.replace(/[<>:"/\\|?*]/g, "_");
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <div className="air-page air-detail">
    <div className="air-detail-toolbar"><Link className="air-button" to={`/ai-reviews${location.search}`}><ArrowLeft size={16} />返回时间轴</Link>{data && <div><button className="air-button" onClick={async () => { try { await copyReviewText(data.content_markdown); setCopyMessage("已复制报告正文"); } catch (error) { setCopyMessage((error as Error).message); } }}><Copy size={15} />复制正文</button><button className="air-button" onClick={downloadMarkdown}><Download size={15} />下载 Markdown</button></div>}</div>
    {copyMessage && <p className="air-notice" role="status">{copyMessage}</p>}
    {report.isPending ? <div className="air-empty"><RefreshCw size={24} className="air-spinning" /><p>正在读取报告…</p></div> : report.isError ? <div className="air-empty" role="alert"><h2>无法读取这份报告</h2><p>{report.error.message}</p><button className="air-button" onClick={() => void report.refetch()}>重试</button></div> : data && <article className="air-document">
      <header className="air-document-header"><div className="air-document-meta"><time dateTime={data.trade_date}>{data.trade_date} 复盘</time><AgentBadge name={data.agent_name} />{data.model && <span>{data.model}</span>}</div><h1>{data.title}</h1><p className="air-muted">提交于 {formatBeijingTime(data.created_at)}（北京时间）{data.data_cutoff && ` · 数据截止 ${formatBeijingTime(data.data_cutoff)}`}</p>{data.tags.length > 0 && <div className="air-tags">{data.tags.map(tag => <span key={tag}>{tag}</span>)}</div>}</header>
      <div className="air-markdown"><ReactMarkdown key={data.id} remarkPlugins={[remarkGfm, remarkCjkFriendly]} rehypePlugins={[rehypeReviewAppendix]} skipHtml components={{
        a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>,
        // 报告为外部 Agent 内容，图片仅展示链接，避免打开报告时自动向第三方发送请求。
        img: ({ src, alt }) => <span className="air-image-link">[图片：{alt || "报告图片"}{src && <> · <a href={src} target="_blank" rel="noopener noreferrer">查看来源</a></>}]</span>,
        table: ({ children }) => <div className="air-table-scroll"><table>{children}</table></div>,
      }}>{data.content_markdown}</ReactMarkdown></div>
      <footer className="air-document-footer"><details className="air-report-info" key={data.id}><summary>归档信息与关联证券</summary>{data.linked_codes.length > 0 && <div><h3>关联证券</h3><div className="air-tags">{data.linked_codes.map(code => <span key={code}>{code}</span>)}</div></div>}{data.data_sources.length > 0 && <div><h3>数据来源</h3><ul>{data.data_sources.map(source => <li key={source}>{source}</li>)}</ul></div>}<p>报告 ID：{data.id}</p></details></footer>
    </article>}
  </div>;
}
