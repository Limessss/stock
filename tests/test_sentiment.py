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
from backend.app.services import panorama_service, sentiment_service
from model.data.sentiment import (
    calculate_local_limit_downs,
    calculate_local_sentiment,
    calculate_local_sentiment_batch,
)


class SentimentTests(unittest.TestCase):
    def test_panorama_presets_persist_range_and_ordered_instruments(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            preset = panorama_service.create_preset(
                session,
                name="机器人主升周期",
                start_date="2026-08-03",
                end_date="2026-08-26",
                instruments=[
                    {"code": "sz000001", "name": "平安银行", "type": "stock"},
                    {"code": "SH000001", "name": "上证指数", "type": "index"},
                    {"code": "SZ000001", "name": "重复项", "type": "stock"},
                ],
            )
            session.commit()

            items = panorama_service.list_presets(session)

            self.assertEqual([item.id for item in items], [preset.id])
            self.assertEqual(items[0].start_date, "2026-08-03")
            self.assertEqual(items[0].end_date, "2026-08-26")
            self.assertEqual(
                items[0].instruments,
                [
                    {"code": "SZ000001", "name": "平安银行", "type": "stock"},
                    {"code": "SH000001", "name": "上证指数", "type": "index"},
                ],
            )
            updated = panorama_service.update_preset(
                session,
                preset.id,
                name="机器人周期（更新）",
                start_date="2026-08-04",
                end_date="2026-08-27",
                instruments=[
                    {"code": f"SH60{index:04d}", "name": f"测试{index}", "type": "stock"}
                    for index in range(105)
                ],
            )
            session.commit()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.name, "机器人周期（更新）")
            self.assertEqual(updated.start_date, "2026-08-04")
            self.assertEqual(len(updated.instruments), 100)
            self.assertIsNone(
                panorama_service.update_preset(
                    session,
                    "missing",
                    name="不存在",
                    start_date="2026-08-04",
                    end_date="2026-08-27",
                    instruments=[],
                )
            )
            self.assertTrue(panorama_service.delete_preset(session, preset.id))
            self.assertFalse(panorama_service.delete_preset(session, "missing"))
            self.assertEqual(panorama_service.list_presets(session), [])

    def test_panorama_preset_rejects_reversed_range(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            with self.assertRaisesRegex(ValueError, "开始日期"):
                panorama_service.create_preset(
                    session,
                    name="无效区间",
                    start_date="2026-08-27",
                    end_date="2026-08-01",
                    instruments=[],
                )

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

    def test_kaipanla_parsers_accept_live_array_shapes(self) -> None:
        payload = {
            "StockList": [
                [
                    [
                        "002084", "海鸥住工", 6, 1788139500, "801787", "实控人变更",
                        1, 0, 1, 0, 0, "6连板", 0, 6, 6,
                    ]
                ]
            ],
            "ZhuShuList": [["803023", "AI应用", 16, 111000000, "000001,000002"]],
        }

        ladder = sentiment_service._parse_ladder(payload)
        self.assertEqual(len(ladder), 1)
        self.assertEqual(ladder[0]["code"], "SZ002084")
        self.assertEqual(ladder[0]["board_count"], 6)
        self.assertEqual(ladder[0]["board_type"], "6连板")
        self.assertEqual(ladder[0]["limit_time"], 1788139500)
        self.assertEqual(ladder[0]["themes"], ["实控人变更"])

        self.assertEqual(
            sentiment_service._parse_theme_counts(payload)[0],
            {"name": "AI应用", "count": 16, "rank": 1},
        )
        self.assertEqual(
            sentiment_service._parse_theme_counts(
                {"List": [["银行", "12,5", 801027]]}
            )[0],
            {"name": "银行", "count": 12, "rank": 1},
        )
        self.assertEqual(
            sentiment_service.kaipanla_client.payload_error(
                {"errcode": 1020, "errmsg": "参数出错"}
            ),
            "errcode=1020: 参数出错",
        )

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

    def test_current_sector_ranking_uses_live_request_shape(self) -> None:
        today = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d")
        with mock.patch.object(settings, "kaipanla_device_id", "test-device"):
            request = sentiment_service.kaipanla_client.build_request(
                "sector_strength", today
            )

        self.assertEqual(request.url, "https://apphq.longhuvip.com/w1/api/index.php")
        self.assertEqual(request.body["apiv"], "w21")
        self.assertEqual(request.body["IsZZ"], "0")
        self.assertNotIn("Date", request.body)

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

            with (
                mock.patch.object(sentiment_service, "_continuous_board_count", return_value=3),
                mock.patch.object(
                    sentiment_service, "get_three_board_origin",
                    side_effect=lambda _cache, code, _date, _name: {
                        "SH601212": "2026-08-21", "SZ002084": "2026-08-24"
                    }[code],
                ),
            ):
                marked = sentiment_service._auto_mark_three_board_origins(
                    session, "2026-08-26"
                )

            self.assertEqual(marked, 2)
            self.assertTrue(session.get(SentimentLadderItem, "silver-first").is_major_first_board)
            self.assertTrue(session.get(SentimentLadderItem, "seagull-first").is_major_first_board)
            self.assertFalse(session.get(SentimentLadderItem, "silver-second").is_major_first_board)

    def test_sync_latest_bootstraps_the_recent_window_in_one_batch(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        dates = ["2026-08-24", "2026-08-25", "2026-08-26"]

        def batch_result(_cache_dir: Path, requested: list[str]) -> dict[str, dict]:
            return {
                date: {
                    "trade_date": date,
                    "up_count": 1,
                    "down_count": 1,
                    "flat_count": 0,
                    "scanned_stock_count": 2,
                    "limit_up_count": 0,
                    "limit_down_count": 0,
                    "limit_down_stocks": [],
                    "broken_board_count": 0,
                    "new_high_100_count": 0,
                    "new_high_stocks": [],
                    "ladder": [],
                    "complete": True,
                }
                for date in requested
            }

        with (
            mock.patch.object(sentiment_service, "_recent_trade_dates", return_value=dates),
            mock.patch.object(
                sentiment_service,
                "calculate_local_sentiment_batch",
                side_effect=batch_result,
            ) as batch,
            mock.patch.object(sentiment_service, "_sync_market_fields"),
            mock.patch.object(
                sentiment_service,
                "_sync_external",
                return_value={"network_requests": 0},
            ),
            mock.patch.object(sentiment_service, "_auto_mark_three_board_origins"),
            Session(engine) as session,
        ):
            result = sentiment_service.sync_latest(session)

            self.assertEqual(result["synced_dates"], dates)
            self.assertEqual(result["latest_trade_date"], "2026-08-26")
            self.assertEqual(result["synced_days"], 3)
            batch.assert_called_once_with(settings.cache_dir, dates)

    def test_sync_latest_only_fills_missing_dates_in_recent_window(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        dates = ["2026-08-24", "2026-08-25", "2026-08-26"]
        missing = ["2026-08-25"]
        local_result = {
            "trade_date": missing[0],
            "up_count": 1,
            "down_count": 1,
            "flat_count": 0,
            "scanned_stock_count": 2,
            "limit_up_count": 0,
            "limit_down_count": 0,
            "limit_down_stocks": [],
            "broken_board_count": 0,
            "new_high_100_count": 0,
            "new_high_stocks": [],
            "ladder": [],
            "complete": True,
        }

        with Session(engine) as session:
            session.add_all(
                [
                    SentimentDaily(
                        trade_date=dates[0],
                        local_complete=True,
                        external_complete=True,
                        external_status="complete",
                    ),
                    SentimentDaily(
                        trade_date=dates[2],
                        local_complete=True,
                        external_complete=True,
                        external_status="complete",
                    ),
                ]
            )
            session.commit()
            with (
                mock.patch.object(sentiment_service, "_recent_trade_dates", return_value=dates),
                mock.patch.object(
                    sentiment_service,
                    "calculate_local_sentiment_batch",
                    return_value={missing[0]: local_result},
                ) as batch,
                mock.patch.object(sentiment_service, "_sync_market_fields"),
                mock.patch.object(
                    sentiment_service,
                    "_sync_external",
                    return_value={"network_requests": 0},
                ),
                mock.patch.object(sentiment_service, "_auto_mark_three_board_origins"),
            ):
                result = sentiment_service.sync_latest(session)

            self.assertEqual(result["synced_dates"], missing)
            self.assertEqual(result["skipped_days"], 2)
            batch.assert_called_once_with(settings.cache_dir, missing)

    def test_sync_latest_retries_external_incomplete_date_without_local_rebuild(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        trade_date = "2026-08-28"

        with Session(engine) as session:
            session.add(
                SentimentDaily(
                    trade_date=trade_date,
                    local_complete=True,
                    external_complete=False,
                    external_status="partial",
                )
            )
            session.commit()

            def complete_external(
                _session: Session,
                daily: SentimentDaily,
                _ladder: list[dict],
                *,
                force: bool,
            ) -> dict:
                self.assertTrue(force)
                daily.external_complete = True
                daily.external_status = "complete"
                return {"network_requests": 3}

            with (
                mock.patch.object(
                    sentiment_service, "_recent_trade_dates", return_value=[trade_date]
                ),
                mock.patch.object(
                    sentiment_service, "calculate_local_sentiment_batch", return_value={}
                ) as batch,
                mock.patch.object(
                    sentiment_service.kaipanla_client, "is_configured", return_value=True
                ),
                mock.patch.object(
                    sentiment_service, "_sync_external", side_effect=complete_external
                ) as external,
                mock.patch.object(sentiment_service, "_auto_mark_three_board_origins"),
            ):
                result = sentiment_service.sync_latest(session)

            batch.assert_called_once_with(settings.cache_dir, [])
            external.assert_called_once()
            self.assertEqual(result["synced_dates"], [trade_date])
            self.assertEqual(result["network_requests"], 3)
            self.assertEqual(result["external_statuses"], {trade_date: "complete"})


if __name__ == "__main__":
    unittest.main()
