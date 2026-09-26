from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.api.ai_reviews import router
from backend.app.core.config import settings
from backend.app.core.database import Base, get_session
from backend.app.models.ai_review import AiReview
from backend.app.models.market import MarketIndexDaily
from backend.app.models.sentiment import (
    ExternalApiSnapshot,
    SentimentDaily,
    SentimentLadderItem,
    SentimentTheme,
)

ROOT = Path(__file__).resolve().parents[1]


def report_payload(**overrides):
    return {
        "trade_date": "2026-09-04",
        "agent_name": "Codex",
        "model": "test-model",
        "title": "观察分歧后的承接",
        "summary": "验证题材强度是否延续。",
        "content_markdown": "## 复盘结论\n\n**先观察，再验证。**\n\n| 方向 | 观察 |\n| --- | --- |\n| 农业 | 持续性 |",
        "tags": ["农业", "分歧"],
        "linked_codes": ["SH600000"],
        "data_sources": ["开盘啦缓存 2026-09-04"],
        "submission_id": str(uuid4()),
        **overrides,
    }


class AiReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.handbook_path = Path(self.temp.name) / "复盘手册.md"
        self.handbook_path.write_text("# 测试手册\n\n按当前版本复盘。", encoding="utf-8")
        handbook_patch = patch.object(settings, "ai_review_handbook_path", self.handbook_path)
        handbook_patch.start()
        self.addCleanup(handbook_patch.stop)
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name).as_posix()}/reviews.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")

        def session_dep():
            with Session(self.engine) as session:
                yield session

        self.app.dependency_overrides[get_session] = session_dep
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def submit(self, payload):
        response = self.client.post("/api/ai-reviews", json=payload)
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()

    def test_multi_agent_same_day_and_new_versions_persist_independently(self):
        first = self.submit(report_payload())
        second = self.submit(report_payload(agent_name="Claude Code"))
        third = self.submit(report_payload(title="补充验证", model="second-model"))
        earlier = self.submit(report_payload(trade_date="2026-09-03", title="昨日复盘"))
        self.assertEqual(4, len({first["id"], second["id"], third["id"], earlier["id"]}))
        result = self.client.get("/api/ai-reviews").json()
        self.assertEqual(4, result["total"])
        self.assertEqual(
            ["2026-09-04"] * 3 + ["2026-09-03"], [r["trade_date"] for r in result["items"]]
        )
        self.assertNotIn("content_markdown", result["items"][0])
        self.assertNotIn("payload_hash", result["items"][0])
        detail = self.client.get(
            first["report_path"].replace("/ai-reviews", "/api/ai-reviews")
        ).json()
        self.assertIn("## 复盘结论", detail["content_markdown"])
        self.assertTrue(detail["created_at"].endswith("Z"))
        # 独立新连接验证真实持久化，不依赖请求/进程内缓存。
        with Session(self.engine) as session:
            self.assertEqual(4, session.scalar(select(func.count()).select_from(AiReview)))
        overview = self.client.get("/api/ai-reviews/overview").json()
        self.assertEqual(2, overview["agent_count"])

    def test_retry_is_idempotent_but_changed_payload_conflicts(self):
        payload = report_payload(submission_id="same-submission")
        first = self.submit(payload)
        retry = self.client.post("/api/ai-reviews", json=payload)
        self.assertEqual(200, retry.status_code)
        self.assertEqual(first["id"], retry.json()["id"])
        self.assertFalse(retry.json()["created"])
        self.assertEqual(
            409,
            self.client.post("/api/ai-reviews", json={**payload, "title": "different"}).status_code,
        )
        self.submit({**payload, "agent_name": "Claude Code"})
        self.assertEqual(2, self.client.get("/api/ai-reviews").json()["total"])

    def test_filter_order_pagination_and_literal_search(self):
        for day, agent, title in [
            ("2026-09-04", "Codex", "100% 强度"),
            ("2026-09-03", "Codex", "其他标题"),
            ("2026-09-02", "Claude Code", "测试"),
        ]:
            self.submit(report_payload(trade_date=day, agent_name=agent, title=title))
        result = self.client.get(
            "/api/ai-reviews", params={"order": "asc", "page_size": 1, "page": 2}
        ).json()
        self.assertEqual(3, result["total"])
        self.assertEqual("2026-09-03", result["items"][0]["trade_date"])
        result = self.client.get(
            "/api/ai-reviews",
            params={"agent_name": "Codex", "start_date": "2026-09-04", "end_date": "2026-09-04"},
        ).json()
        self.assertEqual(1, result["total"])
        self.assertEqual(1, self.client.get("/api/ai-reviews", params={"q": "%"}).json()["total"])
        self.assertEqual(
            422,
            self.client.get(
                "/api/ai-reviews", params={"start_date": "2026-09-04", "end_date": "2026-09-01"}
            ).status_code,
        )
        self.assertEqual(404, self.client.get("/api/ai-reviews/missing").status_code)

    def test_validation_and_explicit_timezone(self):
        for changes in [
            {"content_markdown": "  "},
            {"agent_name": " "},
            {"trade_date": "2026-02-30"},
            {"linked_codes": ["../../config"]},
            {"data_cutoff": "2026-09-04T15:00:00"},
            {"unexpected": 123},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(
                    422,
                    self.client.post("/api/ai-reviews", json=report_payload(**changes)).status_code,
                )
        receipt = self.submit(
            report_payload(data_cutoff="2026-09-04T15:00:00+08:00", tags=[" 农业 ", "农业"])
        )
        detail = self.client.get(f"/api/ai-reviews/{receipt['id']}").json()
        self.assertEqual("2026-09-04T07:00:00Z", detail["data_cutoff"])
        self.assertEqual(["农业"], detail["tags"])

    def seed_context(self):
        with Session(self.engine) as session:
            for day in ("2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07"):
                session.add(SentimentDaily(trade_date=day, local_complete=True, up_count=2000))
                session.add(
                    SentimentLadderItem(
                        id=str(uuid4()),
                        trade_date=day,
                        code="SH600000",
                        name="测试股",
                        board_count=3,
                        board_type="3天3板",
                        themes=["农业"],
                        reason="测试原因",
                        is_major_first_board=True,
                    )
                )
            for n in range(12):
                session.add(
                    SentimentLadderItem(
                        id=str(uuid4()), trade_date="2026-09-04", code=f"SZ{n:06d}", name="样本"
                    )
                )
            session.add(
                ExternalApiSnapshot(
                    id=str(uuid4()),
                    source="kaipanla",
                    endpoint="sector_strength",
                    trade_date="2026-09-04",
                    params_hash="x",
                    status="success",
                    payload={"list": [[f"8{n:05d}", f"板块{n}", 6000 - n, 1.2] for n in range(30)]},
                )
            )
            session.add(
                SentimentTheme(
                    id=str(uuid4()),
                    trade_date="2026-09-04",
                    category="weak_sector",
                    name="芯片",
                    count=-8000,
                    stage="-1.73",
                    rank=1,
                )
            )
            session.add(
                MarketIndexDaily(trade_date="2026-09-04", index_code="SH000001", close=3000)
            )
            session.commit()

    def test_context_cutoff_completeness_and_ranking_semantics(self):
        self.seed_context()
        old = self.submit(report_payload(trade_date="2026-09-03"))
        late = self.submit(report_payload(trade_date="2026-09-03"))
        with Session(self.engine) as session:
            session.get(AiReview, old["id"]).created_at = datetime(2026, 9, 3, 12, tzinfo=UTC)
            session.get(AiReview, late["id"]).created_at = datetime(2026, 9, 5, 12, tzinfo=UTC)
            session.commit()
        result = self.client.get(
            "/api/ai-reviews/context", params={"trade_date": "2026-09-04", "lookback_days": 3}
        ).json()
        self.assertEqual(["2026-09-02", "2026-09-03", "2026-09-04"], result["window_dates"])
        self.assertEqual([old["id"]], [r["id"] for r in result["prior_reports"]])
        self.assertNotIn('"is_major_first_board":', json.dumps(result))
        current = result["days"][-1]
        self.assertTrue(current["ladder"]["truncated"])
        self.assertEqual(5, len(current["strong_sectors"]["items"]))
        detail = self.client.get(
            "/api/ai-reviews/context/day", params={"trade_date": "2026-09-04"}
        ).json()
        self.assertEqual(30, len(detail["strong_sectors"]["items"]))
        self.assertEqual(6000, detail["strong_sectors"]["items"][0]["strength"])
        self.assertEqual(-1.73, detail["weak_sectors"]["items"][0]["change_pct"])
        self.assertEqual(13, len(detail["ladder"]["items"]))
        self.assertIsNone(detail["market"]["total_amount"])
        self.assertFalse(detail["availability"]["market_summary"])
        missing = self.client.get(
            "/api/ai-reviews/context", params={"trade_date": "2026-08-01", "lookback_days": 1}
        ).json()
        self.assertEqual(["2026-08-01"], missing["window_dates"])
        self.assertFalse(missing["days"][0]["availability"]["sentiment"])
        self.assertEqual(0, missing["window_coverage"]["available_days"])
        self.assertEqual(1, missing["window_coverage"]["shortfall_days"])
        default_window = self.client.get(
            "/api/ai-reviews/context", params={"trade_date": "2026-09-04"}
        ).json()
        self.assertEqual(30, default_window["window_coverage"]["requested_days"])
        self.assertEqual(3, default_window["window_coverage"]["available_days"])
        self.assertEqual(27, default_window["window_coverage"]["shortfall_days"])
        self.assertTrue(any("本地仅有 3 个" in caveat for caveat in default_window["caveats"]))

    def test_context_defaults_to_30_data_dates_and_allows_longer_history(self):
        dates = pd.bdate_range(end="2026-09-04", periods=45).strftime("%Y-%m-%d").tolist()
        with Session(self.engine) as session:
            for day in [*dates, "2026-09-07"]:
                session.add(MarketIndexDaily(trade_date=day, index_code="SH000001", close=3000))
            for day in dates[-2:]:
                session.add(SentimentDaily(trade_date=day, local_complete=True))
            session.commit()

        endpoint = "/api/ai-reviews/context"
        default = self.client.get(endpoint, params={"trade_date": "2026-09-04"}).json()
        self.assertEqual(dates[-30:], default["window_dates"])
        coverage = default["window_coverage"]
        self.assertEqual(30, coverage["available_days"])
        self.assertEqual(0, coverage["shortfall_days"])
        self.assertEqual(30, coverage["source_days"]["indices"])
        self.assertEqual(2, coverage["source_days"]["sentiment"])
        self.assertEqual(0, coverage["source_days"]["market_summary"])

        missing_day = self.client.get(endpoint, params={"trade_date": "2026-09-05"}).json()
        self.assertEqual([*dates[-30:], "2026-09-05"], missing_day["window_dates"])
        self.assertEqual(30, missing_day["window_coverage"]["available_days"])
        self.assertFalse(missing_day["window_coverage"]["requested_date_has_data"])
        self.assertEqual("2026-09-04", missing_day["window_coverage"]["data_end_date"])

        for count in (60, 120):
            expanded = self.client.get(
                endpoint, params={"trade_date": "2026-09-04", "lookback_days": count}
            )
            self.assertEqual(200, expanded.status_code)
            self.assertEqual(dates, expanded.json()["window_dates"])
            self.assertEqual(count - 45, expanded.json()["window_coverage"]["shortfall_days"])
        self.assertEqual(422, self.client.get(
            endpoint, params={"trade_date": "2026-09-04", "lookback_days": 121}
        ).status_code)

    def test_stock_history_filters_future_bars_and_reports_actual_end_date(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07"]),
                "open": [10.0, 11.0, 12.0, 13.0],
                "high": [10.0, 11.0, 12.0, 13.0],
                "low": [10.0, 11.0, 12.0, 13.0],
                "close": [10.0, 11.0, 12.0, 13.0],
                "volume": [100.0] * 4,
                "amount": [1000.0] * 4,
            }
        )
        with patch("backend.app.services.kline_service._load_frame", return_value=frame):
            result = self.client.get(
                "/api/ai-reviews/context/stocks/SH600000",
                params={"end_date": "2026-09-05", "bars": 2},
            ).json()
            self.assertEqual(["2026-09-03", "2026-09-04"], [c["time"] for c in result["candles"]])
            self.assertEqual("2026-09-04", result["actual_end_date"])
            self.assertEqual(10.0, result["candles"][0]["change_pct"])
        self.assertEqual(
            422,
            self.client.get(
                "/api/ai-reviews/context/stocks/invalid", params={"end_date": "2026-09-04"}
            ).status_code,
        )

    def test_copy_instructions_contain_date_and_valid_client_configs(self):
        result = self.client.get(
            "/api/ai-reviews/instructions", params={"trade_date": "2026-09-03"}
        ).json()
        self.assertEqual("2026-09-03", result["trade_date"])
        self.assertIn('trade_date="2026-09-03"', result["prompt"])
        self.assertIn('get_review_context(trade_date="2026-09-03", lookback_days=30)', result["prompt"])
        self.assertIn("submit_ai_review", result["prompt"])
        codex = tomllib.loads(result["connection"]["codex_config"])["mcp_servers"]["stockmodel"]
        claude = json.loads(result["connection"]["claude_config"])["mcpServers"]["stockmodel"]
        self.assertEqual(codex["command"], claude["command"])
        self.assertTrue(Path(codex["command"]).exists())
        self.assertTrue(Path(codex["args"][0]).exists())

    def test_instructions_read_updated_handbook_without_reload(self):
        for content in ("# 手册版本甲\n\n旧定义。", "# 手册版本乙\n\n新增角色：阶段领涨。"):
            with self.subTest(content=content):
                raw = content.encode("utf-8-sig")
                self.handbook_path.write_bytes(raw)
                response = self.client.get(
                    "/api/ai-reviews/instructions", params={"trade_date": "2026-09-03"}
                )
                self.assertEqual(200, response.status_code)
                self.assertEqual("no-store", response.headers["cache-control"])
                prompt = response.json()["prompt"]
                self.assertEqual(1, prompt.count(content))
                self.assertIn(hashlib.sha256(raw).hexdigest()[:12], prompt)
        self.assertNotIn("旧定义", prompt)

    def test_unavailable_handbook_does_not_fall_back_to_previous_content(self):
        endpoint = "/api/ai-reviews/instructions?trade_date=2026-09-03"
        self.assertEqual(200, self.client.get(endpoint).status_code)
        for raw in (None, b" \n", b"\xff"):
            with self.subTest(raw=raw):
                if raw is None:
                    self.handbook_path.unlink()
                else:
                    self.handbook_path.write_bytes(raw)
                response = self.client.get(endpoint)
                self.assertEqual(503, response.status_code)
                self.assertEqual("no-store", response.headers["cache-control"])
                self.assertIn("未使用旧副本", response.json()["detail"])
                self.assertNotIn("prompt", response.json())
        self.handbook_path.write_text("# 已恢复手册", encoding="utf-8")
        self.assertIn("# 已恢复手册", self.client.get(endpoint).json()["prompt"])

    def test_real_stdio_mcp_read_submit_retry_and_verify(self):
        self.seed_context()
        # 临时 HTTP 服务与真实 SDK stdio 子进程联通，不读写正式报告库。
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(self.app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(server.started)
            asyncio.run(self._exercise_mcp(port))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()

    async def _exercise_mcp(self, port):
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "backend" / "mcp_server.py")],
            env={
                **os.environ,
                "STOCKMODEL_API_URL": f"http://127.0.0.1:{port}/api",
                "PYTHONUTF8": "1",
            },
            cwd=self.temp.name,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                available_tools = (await session.list_tools()).tools
                names = {tool.name for tool in available_tools}
                self.assertEqual(6, len(names))
                self.assertIn("submit_ai_review", names)
                context_tool = next(tool for tool in available_tools if tool.name == "get_review_context")
                window_schema = context_tool.inputSchema["properties"]["lookback_days"]
                self.assertEqual(30, window_schema["default"])
                self.assertEqual(120, window_schema["maximum"])

                async def call(name, args):
                    response = await session.call_tool(name, args)
                    self.assertFalse(response.isError, response)
                    return response.structuredContent or json.loads(response.content[0].text)

                context = await call(
                    "get_review_context", {"trade_date": "2026-09-04", "lookback_days": 2}
                )
                self.assertEqual(["2026-09-03", "2026-09-04"], context["window_dates"])
                default_context = await call("get_review_context", {"trade_date": "2026-09-04"})
                self.assertEqual(30, default_context["window_coverage"]["requested_days"])
                self.assertEqual(3, default_context["window_coverage"]["available_days"])
                expanded_context = await call(
                    "get_review_context", {"trade_date": "2026-09-04", "lookback_days": 60}
                )
                self.assertEqual(60, expanded_context["window_coverage"]["requested_days"])
                day = await call("get_review_day", {"trade_date": "2026-09-04"})
                self.assertEqual(30, day["strong_sectors"]["total"])
                payload = report_payload()
                receipt = await call("submit_ai_review", {"report": payload})
                retry = await call("submit_ai_review", {"report": payload})
                self.assertEqual(receipt["id"], retry["id"])
                self.assertFalse(retry["created"])
                detail = await call("get_ai_review", {"report_id": receipt["id"]})
                self.assertEqual(payload["content_markdown"], detail["content_markdown"])
                listed = await call("list_ai_reviews", {"end_date": "2026-09-04"})
                self.assertEqual(1, listed["total"])
                prompt = await session.get_prompt(
                    "daily_review", arguments={"trade_date": "2026-09-04"}
                )
                self.assertIn("2026-09-04", prompt.messages[0].content.text)
                updated_handbook = "# MCP 实时手册\n\n同一会话再次读取采用新定义。"
                self.handbook_path.write_bytes(updated_handbook.encode("utf-8"))
                updated_prompt = await session.get_prompt(
                    "daily_review", arguments={"trade_date": "2026-09-04"}
                )
                self.assertIn(updated_handbook, updated_prompt.messages[0].content.text)
                self.assertNotIn("按当前版本复盘", updated_prompt.messages[0].content.text)
                invalid = await session.call_tool(
                    "submit_ai_review", {"report": {"title": "invalid"}}
                )
                self.assertTrue(invalid.isError)


if __name__ == "__main__":
    unittest.main()
