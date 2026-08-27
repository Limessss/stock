from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import Base
from backend.app.models.sentiment import SentimentDaily, SentimentLadderItem
from backend.app.services import sentiment_service
from model.data.sentiment import (
    calculate_local_limit_downs,
    calculate_local_sentiment,
    calculate_local_sentiment_batch,
)


class SentimentTests(unittest.TestCase):
    def test_local_sentiment_calculates_limits_and_new_high(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            (cache_dir / "sh").mkdir(parents=True)
            (cache_dir / "sz").mkdir(parents=True)
            dates = pd.bdate_range(end="2025-12-18", periods=120)

            up = pd.DataFrame(
                {
                    "date": dates,
                    "open": [10.0] * 119 + [11.0],
                    "high": [10.0] * 119 + [11.0],
                    "low": [10.0] * 119 + [11.0],
                    "close": [10.0] * 119 + [11.0],
                }
            )
            down = pd.DataFrame(
                {
                    "date": dates,
                    "open": [10.0] * 119 + [9.0],
                    "high": [10.0] * 119 + [9.0],
                    "low": [10.0] * 119 + [9.0],
                    "close": [10.0] * 119 + [9.0],
                }
            )
            up.to_parquet(cache_dir / "sh" / "SH600001.parquet", index=False)
            down.to_parquet(cache_dir / "sz" / "SZ000001.parquet", index=False)
            (cache_dir / "stock_names.json").write_text(
                json.dumps({"SH600001": "测试上涨", "SZ000001": "测试下跌"}),
                encoding="utf-8",
            )

            result = calculate_local_sentiment(cache_dir, "2025-12-18")

            self.assertEqual(result["limit_up_count"], 1)
            self.assertEqual(result["limit_down_count"], 1)
            self.assertEqual(result["limit_down_stocks"][0]["code"], "SZ000001")
            self.assertEqual(result["new_high_100_count"], 1)
            self.assertEqual(result["ladder"][0]["board_count"], 1)
            self.assertEqual(result["ladder"][0]["board_type"], "一字板")

            batch = calculate_local_sentiment_batch(cache_dir, ["2025-12-18"])
            self.assertEqual(batch["2025-12-18"]["limit_up_count"], 1)
            self.assertEqual(batch["2025-12-18"]["limit_down_count"], 1)
            self.assertEqual(batch["2025-12-18"]["up_count"], 1)
            self.assertEqual(batch["2025-12-18"]["down_count"], 1)

    def test_historical_non_st_limit_ignores_stale_current_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            (cache_dir / "sh").mkdir(parents=True)
            (cache_dir / "sz").mkdir(parents=True)
            dates = pd.to_datetime(["2026-08-12", "2026-08-13"])
            bars = pd.DataFrame(
                {
                    "date": dates,
                    "open": [12.00, 11.78],
                    "high": [12.91, 12.50],
                    "low": [12.00, 11.62],
                    "close": [12.91, 11.62],
                }
            )
            bars.to_parquet(cache_dir / "sz" / "SZ003032.parquet", index=False)
            (cache_dir / "stock_names.json").write_text(
                json.dumps({"SZ003032": "*ST传智"}, ensure_ascii=False),
                encoding="utf-8",
            )

            single = calculate_local_sentiment(cache_dir, "2026-08-13")
            batch = calculate_local_sentiment_batch(cache_dir, ["2026-08-13"])
            limit_downs = calculate_local_limit_downs(cache_dir, ["2026-08-13"])

            self.assertEqual(single["limit_down_count"], 1)
            self.assertEqual(batch["2026-08-13"]["limit_down_count"], 1)
            self.assertEqual(limit_downs["2026-08-13"][0]["code"], "SZ003032")

    def test_exact_five_percent_drop_does_not_infer_st(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            (cache_dir / "sh").mkdir(parents=True)
            (cache_dir / "sz").mkdir(parents=True)
            bars = pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-08-12", "2026-08-13"]),
                    "open": [10.0, 9.8],
                    "high": [10.0, 9.9],
                    "low": [10.0, 9.5],
                    "close": [10.0, 9.5],
                }
            )
            bars.to_parquet(cache_dir / "sz" / "SZ000001.parquet", index=False)
            (cache_dir / "stock_names.json").write_text(
                json.dumps({"SZ000001": "普通股票"}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = calculate_local_sentiment(cache_dir, "2026-08-13")

            self.assertEqual(result["limit_down_count"], 0)

    def test_kaipanla_parsers_accept_common_response_shapes(self) -> None:
        payload = {
            "List": [
                {
                    "StockID": "000001",
                    "StockName": "平安银行",
                    "LianBan": "3板",
                    "Plate": "金融+深圳",
                    "ZhangTingReason": "示例原因",
                }
            ]
        }
        ladder = sentiment_service._parse_ladder(payload)
        self.assertEqual(
            ladder,
            [
                {
                    "code": "SZ000001",
                    "name": "平安银行",
                    "board_count": 3,
                    "board_type": "",
                    "limit_time": None,
                    "reason": "示例原因",
                    "themes": ["金融", "深圳"],
                    "source": "kaipanla",
                }
            ],
        )

        themes = sentiment_service._parse_theme_counts(
            {
                "list": [
                    {"GroupName": "商业航天", "Count": "18"},
                    {"GroupName": "芯片", "Count": 9},
                ]
            }
        )
        self.assertEqual(
            themes[:2],
            [
                {"name": "商业航天", "count": 18, "rank": 1},
                {"name": "芯片", "count": 9, "rank": 2},
            ],
        )

    def test_kaipanla_parsers_accept_history_array_shape(self) -> None:
        payload = {
            "nums": {"ZT": 8, "DT": 2},
            "list": [
                {
                    "ZSName": "商业航天",
                    "num": 2,
                    "StockList": [
                        [
                            "600001", "测试股份", 0, "", 0, 0, 1787707800, 0, 0,
                            "4天3板", 3, "卫星导航、通信", 0, 0, 0, 0,
                            "商业航天", "商业航天+卫星导航；示例原因", 1, "",
                        ]
                    ],
                }
            ],
        }

        ladder = sentiment_service._parse_ladder(payload)
        self.assertEqual(len(ladder), 1)
        self.assertEqual(ladder[0]["code"], "SH600001")
        self.assertEqual(ladder[0]["board_count"], 3)
        self.assertEqual(ladder[0]["board_type"], "4天3板")
        self.assertEqual(ladder[0]["limit_time"], 1787707800)
        self.assertIn("商业航天", ladder[0]["themes"])
        self.assertIn("卫星导航", ladder[0]["themes"])
        self.assertTrue(ladder[0]["reason"].startswith("商业航天"))

        themes = sentiment_service._parse_theme_counts(payload)
        self.assertEqual(themes[0], {"name": "商业航天", "count": 2, "rank": 1})

    def test_sector_ranking_request_and_parser(self) -> None:
        with mock.patch.object(settings, "kaipanla_device_id", "test-device"):
            strong_request = sentiment_service.kaipanla_client.build_request(
                "sector_strength", "2026-08-24"
            )
            weak_request = sentiment_service.kaipanla_client.build_request(
                "sector_weakness", "2026-08-24"
            )

        self.assertEqual(strong_request.body["Order"], "1")
        self.assertEqual(weak_request.body["Order"], "0")
        self.assertEqual(strong_request.body["a"], "RealRankingInfo")
        self.assertEqual(strong_request.body["c"], "ZhiShuRanking")
        self.assertEqual(strong_request.body["Date"], "2026-08-24")
        self.assertEqual(strong_request.body["apiv"], "w43")
        self.assertNotIn("DeviceID", strong_request.public_params)

        rankings = sentiment_service._parse_sector_rankings(
            {
                "list": [
                    ["801572", "中报增长", 6810, -1.091],
                    ["801178", "储能", 3202, -0.948],
                ]
            }
        )
        self.assertEqual(
            rankings,
            [
                {"name": "中报增长", "count": 6810, "rank": 1, "stage": "-1.091"},
                {"name": "储能", "count": 3202, "rank": 2, "stage": "-0.948"},
            ],
        )

    def test_ladder_items_sort_by_limit_time_within_same_board(self) -> None:
        items = [
            {"code": "SH600003", "name": "无时间", "board_count": 3},
            {"code": "SH600002", "name": "晚封板", "board_count": 3, "limit_time": 1787710941},
            {"code": "SH600001", "name": "早封板", "board_count": 3, "limit_time": 1787707500},
        ]

        result = sentiment_service._merge_ladders([], items)

        self.assertEqual([item["name"] for item in result], ["早封板", "晚封板", "无时间"])

    def test_negative_feedback_uses_recent_high_boards_only(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            target = SentimentDaily(
                trade_date="2026-08-27",
                local_complete=True,
                limit_down_stocks=[
                    {"code": "SH600001", "name": "近期高标"},
                    {"code": "SH600002", "name": "过期高标"},
                ],
            )
            session.add_all(
                [
                    target,
                    SentimentDaily(trade_date="2026-08-20", local_complete=True),
                    SentimentDaily(trade_date="2025-12-18", local_complete=True),
                    SentimentLadderItem(
                        id="recent-high",
                        trade_date="2026-08-20",
                        code="SH600001",
                        name="近期高标",
                        board_count=3,
                    ),
                    SentimentLadderItem(
                        id="stale-high",
                        trade_date="2025-12-18",
                        code="SH600002",
                        name="过期高标",
                        board_count=6,
                    ),
                ]
            )
            session.flush()

            result = sentiment_service._negative_feedback_for_day(session, target)

            self.assertEqual([item["code"] for item in result], ["SH600001"])

    def test_external_snapshot_is_requested_once(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        calls = 0

        def fake_fetch(endpoint: str, trade_date: str):
            nonlocal calls
            calls += 1
            request = sentiment_service.kaipanla_client.build_request(endpoint, trade_date)
            return request, {"list": [{"GroupName": "商业航天", "Count": 18}]}

        with (
            mock.patch.object(settings, "kaipanla_enabled", True),
            mock.patch.object(settings, "kaipanla_device_id", "test-device"),
            mock.patch.object(sentiment_service.kaipanla_client, "fetch", fake_fetch),
            Session(engine) as session,
        ):
            first, first_requested = sentiment_service._fetch_snapshot(
                session, "new_high_groups", "2025-12-18", force=False
            )
            session.commit()
            second, second_requested = sentiment_service._fetch_snapshot(
                session, "new_high_groups", "2025-12-18", force=False
            )

        self.assertEqual(first.id, second.id)
        self.assertTrue(first_requested)
        self.assertFalse(second_requested)
        self.assertEqual(calls, 1)

    def test_three_board_stocks_mark_their_latest_first_board(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                [
                    SentimentLadderItem(
                        id="silver-first",
                        trade_date="2026-08-21",
                        code="SH601212",
                        name="白银有色",
                        board_count=1,
                    ),
                    SentimentLadderItem(
                        id="silver-second",
                        trade_date="2026-08-24",
                        code="SH601212",
                        name="白银有色",
                        board_count=2,
                    ),
                    SentimentLadderItem(
                        id="silver-third",
                        trade_date="2026-08-26",
                        code="SH601212",
                        name="白银有色",
                        board_count=3,
                        board_type="4天3板",
                    ),
                    SentimentLadderItem(
                        id="seagull-first",
                        trade_date="2026-08-24",
                        code="SZ002084",
                        name="海鸥住工",
                        board_count=1,
                    ),
                    SentimentLadderItem(
                        id="seagull-third",
                        trade_date="2026-08-26",
                        code="SZ002084",
                        name="海鸥住工",
                        board_count=3,
                    ),
                ]
            )
            session.flush()

            marked = sentiment_service._auto_mark_three_board_origins(
                session, "2026-08-26"
            )

            self.assertEqual(marked, 2)
            self.assertTrue(session.get(SentimentLadderItem, "silver-first").is_major_first_board)
            self.assertTrue(session.get(SentimentLadderItem, "seagull-first").is_major_first_board)
            self.assertFalse(session.get(SentimentLadderItem, "silver-second").is_major_first_board)


if __name__ == "__main__":
    unittest.main()
