import { Node, mergeAttributes } from "@tiptap/core";

/** 内联股票标签：编辑态蓝色可点击，序列化为 span.stock-mention */
export const StockMention = Node.create({
  name: "stockMention",
  group: "inline",
  inline: true,
  atom: true,
  selectable: false,

  addAttributes() {
    return {
      code: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute("data-code"),
      },
      name: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute("data-name"),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span.stock-mention" }];
  },

  renderHTML({ node, HTMLAttributes }) {
    const name = String(node.attrs.name ?? "");
    const code = String(node.attrs.code ?? "");
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        class: "stock-mention",
        "data-code": code,
        "data-name": name,
      }),
      `#${name}`,
    ];
  },

  renderText({ node }) {
    return `#${node.attrs.name ?? ""}`;
  },
});
