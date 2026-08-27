import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Card,
  Input,
  Select,
  Space,
  Spin,
  Switch,
  Typography,
} from "@/components/ui";
import { ArrowLeftOutlined, SaveOutlined } from "@/components/ui/icons";
import { useNavigate, useParams } from "react-router-dom";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

import { createNote, getNote, updateNote } from "@/api/notes";
import ChineseDatePicker from "@/components/ChineseDatePicker";
import NoteContentView from "@/components/NoteContentView";
import NoteEditor from "@/components/NoteEditor";
import StockKlineModal, { type StockKlineTarget } from "@/components/StockKlineModal";
import { linkifyStockMentions } from "@/lib/stockMention";

const { Title } = Typography;

export default function ReviewNoteEditorPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === "new" || !id;
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState("");
  const [contentHtml, setContentHtml] = useState("<p></p>");
  const [tradeDate, setTradeDate] = useState<Dayjs | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [preview, setPreview] = useState(false);
  const [loaded, setLoaded] = useState(isNew);
  const [klineOpen, setKlineOpen] = useState(false);
  const [klineStock, setKlineStock] = useState<StockKlineTarget | null>(null);

  const noteQ = useQuery({
    queryKey: ["note", id],
    queryFn: () => getNote(id!),
    enabled: !isNew && !!id,
  });

  useEffect(() => {
    if (!noteQ.data) return;
    const n = noteQ.data;
    setTitle(n.title);
    setTradeDate(n.trade_date ? dayjs(n.trade_date) : null);
    setTags(n.tags ?? []);
    setLoaded(true);
    linkifyStockMentions(n.content_html || "<p></p>").then((html) => {
      setContentHtml(html);
    });
  }, [noteQ.data]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const linked = await linkifyStockMentions(contentHtml);
      const payload = {
        title,
        content_html: linked,
        trade_date: tradeDate ? tradeDate.format("YYYY-MM-DD") : null,
        tags,
      };
      if (isNew) {
        return createNote(payload);
      }
      return updateNote(id!, payload);
    },
    onSuccess: (note) => {
      message.success("已保存");
      setContentHtml(note.content_html);
      queryClient.invalidateQueries({ queryKey: ["notes"] });
      queryClient.invalidateQueries({ queryKey: ["note-tags"] });
      if (isNew) {
        navigate(`/notes/${note.id}`, { replace: true });
      } else {
        queryClient.setQueryData(["note", note.id], note);
      }
    },
    onError: (e: Error) => message.error(e.message),
  });

  const openKline = useCallback(
    (stock: StockKlineTarget) => {
      setKlineStock({
        ...stock,
        signalDate: tradeDate?.format("YYYY-MM-DD") ?? stock.signalDate,
      });
      setKlineOpen(true);
    },
    [tradeDate]
  );

  if (!isNew && noteQ.isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!isNew && noteQ.error) {
    return (
      <Card>
        <Typography.Text type="danger">加载失败：{(noteQ.error as Error).message}</Typography.Text>
      </Card>
    );
  }

  if (!loaded && !isNew) {
    return null;
  }

  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }} wrap>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/notes")}>
            返回列表
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            {isNew ? "新建笔记" : "编辑笔记"}
          </Title>
        </Space>
        <Space>
          <span style={{ fontSize: 13, color: "#666" }}>预览</span>
          <Switch checked={preview} onChange={setPreview} />
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saveMut.isPending}
            onClick={() => saveMut.mutate()}
          >
            保存
          </Button>
        </Space>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          <Input
            placeholder="标题"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            size="large"
          />
          <Space wrap>
            <Space>
              <span style={{ color: "#666" }}>复盘日期</span>
              <ChineseDatePicker
                value={tradeDate}
                onChange={setTradeDate}
                allowClear
                placeholder="可选"
              />
            </Space>
            <Space>
              <span style={{ color: "#666" }}>标签</span>
              <Select
                mode="tags"
                style={{ minWidth: 240 }}
                placeholder="输入后回车添加"
                value={tags}
                onChange={setTags}
                tokenSeparators={[","]}
              />
            </Space>
          </Space>
        </Space>
      </Card>

      <Card>
        {preview ? (
          <NoteContentView
            html={contentHtml}
            tradeDate={tradeDate?.format("YYYY-MM-DD")}
            onStockClick={openKline}
          />
        ) : (
          <NoteEditor
            key={isNew ? "new" : `${id}-${loaded}`}
            value={contentHtml}
            onChange={setContentHtml}
            minHeight={480}
            tradeDate={tradeDate?.format("YYYY-MM-DD")}
            onStockClick={openKline}
          />
        )}
      </Card>

      <StockKlineModal
        open={klineOpen}
        stock={klineStock}
        onClose={() => setKlineOpen(false)}
      />
    </div>
  );
}
