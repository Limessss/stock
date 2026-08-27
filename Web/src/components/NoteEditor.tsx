import { useCallback, useEffect, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { Button, Space, Tooltip } from "@/components/ui";
import {
  BoldOutlined,
  ItalicOutlined,
  OrderedListOutlined,
  StrikethroughOutlined,
  UnorderedListOutlined,
} from "@/components/ui/icons";

import type { StockSearchItem } from "@/api/stocks";
import { linkifyStockMentions } from "@/lib/stockMention";
import StockMentionMenu from "@/components/StockMentionMenu";
import type { StockKlineTarget } from "@/components/StockKlineModal";
import { StockMention } from "@/components/tiptap/StockMentionExtension";

interface Props {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  minHeight?: number;
  tradeDate?: string | null;
  onStockClick?: (stock: StockKlineTarget) => void;
}

function isHashKey(e: KeyboardEvent): boolean {
  return e.key === "#" || (e.code === "Digit3" && e.shiftKey);
}

export default function NoteEditor({
  value,
  onChange,
  placeholder = "写点什么… 输入 # 可插入股票（如 #东方环宇）",
  minHeight = 360,
  tradeDate,
  onStockClick,
}: Props) {
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionIdx, setMentionIdx] = useState(0);
  const mentionOpenRef = useRef(false);
  const onChangeRef = useRef(onChange);
  const onStockClickRef = useRef(onStockClick);
  const tradeDateRef = useRef(tradeDate);
  const syncingRef = useRef(false);

  useEffect(() => {
    mentionOpenRef.current = mentionOpen;
  }, [mentionOpen]);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);
  useEffect(() => {
    onStockClickRef.current = onStockClick;
  }, [onStockClick]);
  useEffect(() => {
    tradeDateRef.current = tradeDate;
  }, [tradeDate]);

  const openMention = useCallback(() => {
    setMentionOpen(true);
    setMentionQuery("");
    setMentionIdx(0);
  }, []);

  const closeMention = useCallback(() => {
    setMentionOpen(false);
    setMentionQuery("");
    setMentionIdx(0);
  }, []);

  const editor = useEditor({
    extensions: [
      StarterKit,
      StockMention,
      Placeholder.configure({ placeholder }),
    ],
    content: value || "<p></p>",
    onUpdate: ({ editor: ed }) => {
      if (syncingRef.current) return;
      onChangeRef.current(ed.getHTML());
    },
    onBlur: ({ editor: ed }) => {
      linkifyStockMentions(ed.getHTML()).then((linked) => {
        if (linked === ed.getHTML()) return;
        syncingRef.current = true;
        ed.commands.setContent(linked, { emitUpdate: true });
        syncingRef.current = false;
        onChangeRef.current(linked);
      });
    },
    editorProps: {
      handleKeyDown: (_view, event) => {
        if (mentionOpenRef.current) return false;
        if (!isHashKey(event) || event.ctrlKey || event.metaKey || event.altKey) {
          return false;
        }
        event.preventDefault();
        openMention();
        return true;
      },
      handleClick: (_view, _pos, event) => {
        const el = (event.target as HTMLElement).closest(".stock-mention");
        if (!el) return false;
        event.preventDefault();
        const code = el.getAttribute("data-code");
        if (!code || !onStockClickRef.current) return true;
        onStockClickRef.current({
          code: code.toUpperCase(),
          name: el.getAttribute("data-name") ?? undefined,
          signalDate: tradeDateRef.current ?? undefined,
        });
        return true;
      },
    },
  });

  const insertStock = useCallback(
    (item: StockSearchItem) => {
      if (!editor) return;
      editor
        .chain()
        .focus()
        .insertContent({
          type: "stockMention",
          attrs: { code: item.code.toUpperCase(), name: item.name },
        })
        .insertContent(" ")
        .run();
      closeMention();
    },
    [closeMention, editor]
  );

  useEffect(() => {
    if (!editor || !value) return;
    const current = editor.getHTML();
    if (value !== current) {
      syncingRef.current = true;
      editor.commands.setContent(value, { emitUpdate: false });
      syncingRef.current = false;
    }
  }, [editor, value]);

  if (!editor) return null;

  return (
    <div className="note-editor-wrap tiptap-note-editor">
      <div className="tiptap-toolbar">
        <Space wrap size={4}>
          <Tooltip title="加粗">
            <Button
              type={editor.isActive("bold") ? "primary" : "text"}
              size="small"
              icon={<BoldOutlined />}
              onClick={() => editor.chain().focus().toggleBold().run()}
            />
          </Tooltip>
          <Tooltip title="斜体">
            <Button
              type={editor.isActive("italic") ? "primary" : "text"}
              size="small"
              icon={<ItalicOutlined />}
              onClick={() => editor.chain().focus().toggleItalic().run()}
            />
          </Tooltip>
          <Tooltip title="删除线">
            <Button
              type={editor.isActive("strike") ? "primary" : "text"}
              size="small"
              icon={<StrikethroughOutlined />}
              onClick={() => editor.chain().focus().toggleStrike().run()}
            />
          </Tooltip>
          <Tooltip title="无序列表">
            <Button
              type={editor.isActive("bulletList") ? "primary" : "text"}
              size="small"
              icon={<UnorderedListOutlined />}
              onClick={() => editor.chain().focus().toggleBulletList().run()}
            />
          </Tooltip>
          <Tooltip title="有序列表">
            <Button
              type={editor.isActive("orderedList") ? "primary" : "text"}
              size="small"
              icon={<OrderedListOutlined />}
              onClick={() => editor.chain().focus().toggleOrderedList().run()}
            />
          </Tooltip>
        </Space>
      </div>
      <EditorContent
        editor={editor}
        className="tiptap-editor-body"
        style={{ minHeight }}
      />
      <StockMentionMenu
        open={mentionOpen}
        query={mentionQuery}
        activeIdx={mentionIdx}
        onQueryChange={setMentionQuery}
        onActiveIdxChange={setMentionIdx}
        onSelect={insertStock}
        onClose={closeMention}
      />
    </div>
  );
}
