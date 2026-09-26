type MarkdownNode = {
  type: string;
  tagName?: string;
  value?: string;
  children?: MarkdownNode[];
  properties?: Record<string, unknown>;
};

function nodeText(node: MarkdownNode): string {
  return node.value ?? node.children?.map(nodeText).join("") ?? "";
}

/** 在 Markdown 已解析、引用已解析后折叠附录，完整原文仍用于复制和下载。 */
export function rehypeReviewAppendix() {
  return (tree: MarkdownNode) => {
    if (!tree.children) return;
    const nodes = tree.children;
    const result: MarkdownNode[] = [];
    for (let index = 0; index < nodes.length; index += 1) {
      const node = nodes[index];
      const title = nodeText(node).trim();
      // 仅匹配顶层的明确二级标题；代码块、引用和普通章节不参与折叠。
      if (node.type !== "element" || node.tagName !== "h2" || !/^(?:(?:[一二三四五六七八九十百]+|\d+)[、.．]\s*)?(?:附录[：:]\s*)?数据与依据$/u.test(title)) {
        result.push(node);
        continue;
      }
      let end = index + 1;
      while (end < nodes.length && !(nodes[end].type === "element" && /^h[12]$/.test(nodes[end].tagName ?? ""))) end += 1;
      result.push({
        type: "element",
        tagName: "details",
        properties: { className: ["air-evidence"] },
        children: [
          { type: "element", tagName: "summary", properties: {}, children: [{ type: "text", value: "数据与依据" }] },
          { type: "element", tagName: "div", properties: { className: ["air-evidence-content"] }, children: nodes.slice(index + 1, end) },
        ],
      });
      index = end - 1;
    }
    tree.children = result;
  };
}
