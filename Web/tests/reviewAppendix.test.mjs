import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkCjkFriendly from "remark-cjk-friendly/parseOnly";
import { rehypeReviewAppendix } from "../src/lib/reviewAppendix.ts";

const render = (markdown) => renderToStaticMarkup(createElement(ReactMarkdown, {
  remarkPlugins: [remarkGfm, remarkCjkFriendly], rehypePlugins: [rehypeReviewAppendix], skipHtml: true,
}, markdown));

test("旧版和新版附录默认关闭，完整表格保留在可展开区域", () => {
  for (const title of ["数据与依据", "八、数据与依据", "8. 数据与依据", "附录：数据与依据"]) {
    const html = render(`主要判断\n\n## ${title}\n\n### 名单\n\n| 名称 | 涨幅 |\n| --- | --- |\n| 样本 | 5% |`);
    assert.match(html, /^<p>主要判断<\/p>[\s\S]*<details class="air-evidence">/);
    assert.match(html, /<summary>数据与依据<\/summary>[\s\S]*<table>[\s\S]*样本[\s\S]*<\/details>/);
    assert.doesNotMatch(html, /<details[^>]*\bopen\b/);
  }
});

test("正文、代码块、引用中的同名文字不误折叠，后续正式章节保持可见", () => {
  const html = render("普通数据与依据\n\n```md\n## 数据与依据\n```\n\n> ## 数据与依据\n\n## 数据与依据\n\n来源\n\n## 下一交易日\n\n重要观察");
  assert.equal((html.match(/<details/g) ?? []).length, 1);
  assert.match(html, /<pre>[\s\S]*## 数据与依据[\s\S]*<\/pre>/);
  assert.match(html, /<blockquote>[\s\S]*<h2>数据与依据<\/h2>[\s\S]*<\/blockquote>/);
  assert.match(html, /<\/details>[\s\S]*<h2>下一交易日<\/h2>[\s\S]*重要观察/);
});

test("附录中的引用定义仍能服务正文链接；外部原始 HTML 不执行", () => {
  const html = render("核对[来源][source]\n\n## 数据与依据\n\n[source]: https://example.com/quote\n\n<script>alert(1)</script>\n\n<img src=\"https://example.com/tracker\">\n\n来源说明");
  assert.match(html, /<a href="https:\/\/example.com\/quote">来源<\/a>/);
  assert.doesNotMatch(html, /<script|<img/);
  assert.match(html, /来源说明[\s\S]*<\/details>/);
});

test("没有约定附录标题时保留原有内容与标题", () => {
  const html = render("## 市场\n\n现状\n\n## 附录其他分析\n\n关键反证");
  assert.doesNotMatch(html, /<details/);
  assert.match(html, /<h2>附录其他分析<\/h2>[\s\S]*关键反证/);
});

test("中文标点后的加粗正常显示，代码和转义的星号仍保留", () => {
  const html = render("**转折在9月9—11日。**亚盛开始回落。\n\n`**代码。**`\n\n\\*\\*原样。\\*\\*中文\n\n## 数据与依据\n\n**原名单。**全部保留。");
  assert.match(html, /<strong>转折在9月9—11日。<\/strong>亚盛开始回落。/);
  assert.match(html, /<code>\*\*代码。\*\*<\/code>/);
  assert.match(html, /<p>\*\*原样。\*\*中文<\/p>/);
  assert.match(html, /<details[\s\S]*<strong>原名单。<\/strong>全部保留。/);
});
