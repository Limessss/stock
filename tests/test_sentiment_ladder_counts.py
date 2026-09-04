from __future__ import annotations

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
from backend.app.schemas.sentiment import SentimentDay
from backend.app.services import sentiment_service
from model.data.sentiment import get_continuous_board_count


class LadderCountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache_dir = Path(self.temp.name)
        (self.cache_dir / "sh").mkdir()
        self.path = self.cache_dir / "sh" / "SH603123.parquet"
        # 涨停、断板、平盘、重新首板、连续二板。
        self.dates = pd.bdate_range("2026-08-28", periods=6)
        self.closes = [10, 11, 10, 10, 11, 12.1]
        self.write_prices()

    def write_prices(self) -> None:
        pd.DataFrame({
            "date": self.dates,
            **{field: self.closes for field in ("open", "high", "low", "close")},
        }).to_parquet(self.path)

    def test_cached_labels_use_actual_streak_in_day_and_matrix(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with mock.patch.object(settings, "cache_dir", self.cache_dir), Session(engine) as session:
            for date, count, label in [
                ("2026-09-03", 2, "4天2板"),
                ("2026-09-04", 3, "5天3板"),
            ]:
                session.add(SentimentDaily(trade_date=date, local_complete=True))
                session.add(SentimentLadderItem(
                    id=date, trade_date=date, code="SH603123", name="翠微股份",
                    board_count=count, board_type=label, source="kaipanla",
                    reason="数字货币", themes=["数字货币"], limit_time=1788485402,
                ))
            session.commit()
            days = sentiment_service.get_matrix(session, limit=2)
            for day, expected, label in zip(days, [1, 2], ["4天2板", "5天3板"]):
                parsed = SentimentDay.model_validate(day)
                stock = parsed.ladder.items[0]
                self.assertEqual(stock.continuous_board_count, expected)
                self.assertEqual(stock.board_type, label)
                self.assertEqual(stock.board_count, expected + 1)
                self.assertEqual(stock.reason, "数字货币")
                self.assertEqual(stock.limit_time, 1788485402)
                self.assertEqual(parsed.ladder.max_board, expected)
                self.assertEqual(parsed.ladder.three_board_count, 0)
            updated = sentiment_service.set_major_first_boards(session, "2026-09-03", ["SH603123"])
            self.assertTrue(updated["ladder"]["items"][0]["is_major_first_board"])

    def test_missing_history_does_not_turn_interval_count_into_streak(self) -> None:
        with mock.patch.object(settings, "cache_dir", self.cache_dir):
            for label in ("4天2板", "反包板", "断板反包"):
                item = SentimentLadderItem(
                    code="SH600999", trade_date="2026-09-04", name="测试",
                    board_count=2, board_type=label,
                )
                self.assertIsNone(sentiment_service._continuous_board_count(item))
            item.board_type = "2连板"
            self.assertEqual(sentiment_service._continuous_board_count(item), 2)

    def test_streak_cache_refreshes_when_prices_change(self) -> None:
        self.assertEqual(get_continuous_board_count(self.cache_dir, "SH603123", "2026-09-04"), 2)
        self.closes[-1] = 11
        self.write_prices()
        self.assertEqual(get_continuous_board_count(self.cache_dir, "SH603123", "2026-09-04"), 0)
        self.assertIsNone(get_continuous_board_count(self.cache_dir, "SH603123", "2026-09-07"))

    def test_auto_origin_stays_in_current_run_and_ignores_cumulative_three(self) -> None:
        self.dates = pd.bdate_range("2026-08-28", periods=7)
        self.closes = [10, 11, 10, 10, 11, 12.1, 13.31]
        self.write_prices()
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with mock.patch.object(settings, "cache_dir", self.cache_dir), Session(engine) as session:
            for date, count, label in [
                ("2026-08-31", 1, "首板"),
                ("2026-09-03", 2, "4天2板"),
                ("2026-09-04", 3, "5天3板"),
                ("2026-09-07", 4, "6天4板"),
            ]:
                session.add(SentimentLadderItem(
                    id=date, trade_date=date, code="SH603123", name="翠微股份",
                    board_count=count, board_type=label,
                ))
            session.flush()
            self.assertEqual(sentiment_service._auto_mark_three_board_origins(session, "2026-09-04"), 0)
            # 旧规则误标了上一轮首板，重算计划必须移除并补上当前首板。
            session.get(SentimentLadderItem, "2026-08-31").is_major_first_board = True
            session.flush()
            changes = sentiment_service.plan_major_first_board_repair(session)
            self.assertEqual(
                {(item["trade_date"], item["before"], item["after"]) for item in changes},
                {("2026-08-31", True, False), ("2026-09-03", False, True)},
            )
            self.assertTrue(session.get(SentimentLadderItem, "2026-08-31").is_major_first_board)
            session.get(SentimentLadderItem, "2026-08-31").is_major_first_board = False
            self.assertEqual(sentiment_service._auto_mark_three_board_origins(session, "2026-09-07"), 1)
            self.assertTrue(session.get(SentimentLadderItem, "2026-09-03").is_major_first_board)
            self.assertFalse(session.get(SentimentLadderItem, "2026-08-31").is_major_first_board)
            self.assertEqual(sentiment_service._auto_mark_three_board_origins(session, "2026-09-07"), 0)

            # 本轮首板快照缺失时不能把标记落到上一次首板。
            session.delete(session.get(SentimentLadderItem, "2026-09-03"))
            session.flush()
            self.assertEqual(sentiment_service._auto_mark_three_board_origins(session, "2026-09-07"), 0)
            self.assertFalse(session.get(SentimentLadderItem, "2026-08-31").is_major_first_board)

            # 缺少行情时也不靠累计板数猜测。
            self.path.unlink()
            self.assertEqual(sentiment_service._auto_mark_three_board_origins(session, "2026-09-07"), 0)


if __name__ == "__main__":
    unittest.main()
