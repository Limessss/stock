import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Card,
  Empty,
  Input,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from "@/components/ui";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@/components/ui/icons";
import { Link, useNavigate } from "react-router-dom";
import { nowBeijing, parseApiTime, parseBeijingDate } from "@/lib/dayjsSetup";

import { deleteNote, listNoteTags, listNotes, type NoteSummary } from "@/api/notes";
import { fetchMarketOverviews } from "@/api/market";
import MarketDayOverview from "@/components/MarketDayOverview";
import NoteExcerpt from "@/components/NoteExcerpt";
import StockKlineModal, { type StockKlineTarget } from "@/components/StockKlineModal";

const { Title, Text } = Typography;

function noteGroupDate(note: NoteSummary): string {
  return note.trade_date ?? parseApiTime(note.updated_at).format("YYYY-MM-DD");
}

function formatTimelineLabel(dateStr: string): string {
  const d = parseBeijingDate(dateStr);
  const today = nowBeijing().startOf("day");
  const diff = today.diff(d.startOf("day"), "day");
  const base = d.format("YYYY年MM月DD日 dddd");
  if (diff === 0) return `今天 · ${base}`;
  if (diff === 1) return `昨天 · ${base}`;
  if (diff < 7) return `${diff} 天前 · ${base}`;
  return base;
}

function groupNotesByDate(notes: NoteSummary[]): [string, NoteSummary[]][] {
  const map = new Map<string, NoteSummary[]>();
  for (const note of notes) {
    const key = noteGroupDate(note);
    const list = map.get(key);
    if (list) list.push(note);
    else map.set(key, [note]);
  }
  return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]));
}

export default function ReviewNotesPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [q, setQ] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [tag, setTag] = useState<string | undefined>();
  const [code, setCode] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [klineOpen, setKlineOpen] = useState(false);
  const [klineStock, setKlineStock] = useState<StockKlineTarget | null>(null);

  const tagsQ = useQuery({
    queryKey: ["note-tags"],
    queryFn: listNoteTags,
  });

  const notesQ = useQuery({
    queryKey: ["notes", searchQ, tag, code, page],
    queryFn: () =>
      listNotes({
        q: searchQ,
        tag: tag ?? "",
        code,
        page,
        page_size: pageSize,
      }),
  });

  const deleteMut = useMutation({
    mutationFn: deleteNote,
    onSuccess: () => {
      message.success("已删除");
      queryClient.invalidateQueries({ queryKey: ["notes"] });
      queryClient.invalidateQueries({ queryKey: ["note-tags"] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const tagOptions = useMemo(
    () => (tagsQ.data ?? []).map((t) => ({ label: t, value: t })),
    [tagsQ.data]
  );

  const groupedNotes = useMemo(
    () => groupNotesByDate(notesQ.data?.items ?? []),
    [notesQ.data?.items]
  );

  const timelineDates = useMemo(
    () => groupedNotes.map(([d]) => d),
    [groupedNotes]
  );

  const marketQ = useQuery({
    queryKey: ["market-overview", timelineDates],
    queryFn: () => fetchMarketOverviews(timelineDates),
    enabled: timelineDates.length > 0,
    staleTime: 60_000,
  });

  const openKline = useCallback((stock: StockKlineTarget, tradeDate?: string | null) => {
    setKlineStock({
      ...stock,
      signalDate: tradeDate ?? stock.signalDate,
    });
    setKlineOpen(true);
  }, []);

  const onSearch = () => {
    setSearchQ(q.trim());
    setPage(1);
  };

  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }} wrap>
        <Title level={3} style={{ margin: 0 }}>
          复盘笔记
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/notes/new")}>
          新建笔记
        </Button>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="搜索标题或正文"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onPressEnter={onSearch}
            style={{ width: 220 }}
            allowClear
          />
          <Select
            placeholder="按标签筛选"
            allowClear
            style={{ width: 160 }}
            options={tagOptions}
            value={tag}
            onChange={(v) => {
              setTag(v);
              setPage(1);
            }}
          />
          <Input
            placeholder="按股票代码"
            value={code}
            onChange={(e) => {
              setCode(e.target.value.toUpperCase());
              setPage(1);
            }}
            style={{ width: 140 }}
            allowClear
          />
          <Button icon={<SearchOutlined />} onClick={onSearch}>
            搜索
          </Button>
        </Space>
      </Card>

      {notesQ.isLoading && (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin />
        </div>
      )}

      {!notesQ.isLoading && (notesQ.data?.items.length ?? 0) === 0 && (
        <Empty description="暂无笔记">
          <Button type="primary" onClick={() => navigate("/notes/new")}>
            写第一篇
          </Button>
        </Empty>
      )}

      {!notesQ.isLoading && groupedNotes.length > 0 && (
        <div className="note-timeline-wrap">
          <Timeline mode="left">
            {groupedNotes.map(([dateStr, notes]) =>
              notes.map((note, idx) => (
                <Timeline.Item
                  key={note.id}
                  label={idx === 0 ? formatTimelineLabel(dateStr) : undefined}
                  color={idx === 0 ? "blue" : "gray"}
                >
                  {idx === 0 && (
                    <MarketDayOverview
                      data={marketQ.data?.items[dateStr]}
                      loading={marketQ.isLoading}
                    />
                  )}
                  <Card className="note-timeline-card" size="small">
                    <div className="note-timeline-card-head">
                      <Link to={`/notes/${note.id}`} className="note-timeline-title">
                        {note.title || "无标题"}
                      </Link>
                      <Space size={4}>
                        <Link to={`/notes/${note.id}`}>
                          <Button type="text" size="small" icon={<EditOutlined />} />
                        </Link>
                        <Popconfirm
                          title="确定删除这篇笔记？"
                          onConfirm={() => deleteMut.mutate(note.id)}
                        >
                          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    </div>

                    {note.trade_date && note.trade_date !== dateStr && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        复盘日 {note.trade_date}
                      </Text>
                    )}

                    <div className="note-list-excerpt-wrap">
                      <NoteExcerpt
                        text={note.excerpt}
                        mentions={note.mentions}
                        onStockClick={(stock) => openKline(stock, note.trade_date)}
                      />
                    </div>

                    <Space wrap size={[4, 4]}>
                      {note.tags.map((t) => (
                        <Tag key={t}>{t}</Tag>
                      ))}
                      {note.linked_codes.map((c) => {
                        const name =
                          note.mentions?.find((m) => m.code === c)?.name ?? c;
                        return (
                          <Tag
                            key={c}
                            color="blue"
                            style={{ cursor: "pointer" }}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              openKline({ code: c, name }, note.trade_date);
                            }}
                          >
                            #{name !== c ? name : c}
                          </Tag>
                        );
                      })}
                    </Space>

                    <div className="note-timeline-meta">
                      更新于 {parseApiTime(note.updated_at).format("HH:mm")}
                    </div>
                  </Card>
                </Timeline.Item>
              ))
            )}
          </Timeline>
        </div>
      )}

      {(notesQ.data?.total ?? 0) > pageSize && (
        <div style={{ marginTop: 16, textAlign: "right" }}>
          <Pagination
            current={page}
            pageSize={pageSize}
            total={notesQ.data?.total ?? 0}
            onChange={setPage}
            showSizeChanger={false}
          />
        </div>
      )}

      <StockKlineModal
        open={klineOpen}
        stock={klineStock}
        onClose={() => setKlineOpen(false)}
      />
    </div>
  );
}
