from unittest import TestCase, mock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.core import database
from backend.app.models.sentiment import SentimentDaily
from backend.app.services import sentiment_service


class SentimentSummaryTests(TestCase):
    def test_summary_persists_per_date_survives_sync_and_can_be_cleared(self):
        engine = create_engine("sqlite:///:memory:")
        database.Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all([
                SentimentDaily(trade_date="2026-09-14", local_complete=True),
                SentimentDaily(trade_date="2026-09-15", local_complete=True),
            ])
            session.commit()
            self.assertTrue(sentiment_service.set_summary(session, "2026-09-14", "人工总结\n第二行"))
            self.assertFalse(sentiment_service.set_summary(session, "2026-09-16", "不存在"))
        with Session(engine) as session:
            daily = session.get(SentimentDaily, "2026-09-14")
            sentiment_service._apply_local_result(session, daily, {
                "limit_up_count": 0, "limit_down_count": 0, "limit_down_stocks": [],
                "broken_board_count": 0, "new_high_100_count": 0,
                "scanned_stock_count": 0, "new_high_stocks": [], "complete": True,
                "ladder": [],
            })
            session.commit()
            with mock.patch.object(sentiment_service, "_market_volume", return_value=(None, None)):
                days = sentiment_service.get_matrix(session)
            self.assertEqual([day["summary"] for day in days], ["人工总结\n第二行", ""])
            self.assertTrue(sentiment_service.set_summary(session, "2026-09-14", ""))
            session.expire_all()
            self.assertEqual(session.get(SentimentDaily, "2026-09-14").summary, "")

    def test_migration_preserves_existing_rows_and_is_repeatable(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE sentiment_daily (trade_date TEXT PRIMARY KEY)"))
            connection.execute(text("INSERT INTO sentiment_daily VALUES ('2026-09-14')"))
        with mock.patch.object(database, "engine", engine):
            database._migrate_columns()
            database._migrate_columns()
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT summary FROM sentiment_daily")).scalar_one(), "")
