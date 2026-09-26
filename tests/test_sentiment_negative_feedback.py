from unittest import TestCase, mock
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.core.database import Base
from backend.app.models.sentiment import SentimentDaily, SentimentLadderItem
from backend.app.services import sentiment_service as service


class NegativeFeedbackTests(TestCase):
    def test_windows_streaks_and_deduplication(self):
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        dates = pd.bdate_range(end="2026-09-24", periods=63).strftime("%Y-%m-%d").tolist()
        with Session(engine) as session:
            session.add_all([SentimentDaily(trade_date=d, local_complete=True) for d in dates])
            session.flush()
            target = session.get(SentimentDaily, dates[-1])
            cases = [
                ("SH600001", 10, 3, "3连板"),
                ("SH600002", 11, 3, "3连板"),
                ("SH600003", 60, 5, "5连板"),
                ("SH600004", 61, 6, "6连板"),
                ("SH600005", 20, 6, "7天6板"),
                ("SH600006", 20, 5, "5连板"),
                ("SH600006", 2, 3, "3连板"),
                ("SH600007", 1, 6, "7天6板"),
                ("SH600008", 0, 6, "6连板"),
                ("SH600009", 1, 5, "5连板"),
            ]
            target.limit_down_stocks = [{"code": f"SH60000{i}"} for i in range(1, 9)]
            for index, (code, ago, height, label) in enumerate(cases):
                session.add(SentimentLadderItem(id=str(index), trade_date=dates[-1-ago], code=code, board_count=height, board_type=label))
            session.flush()
            with mock.patch.object(service, "get_continuous_board_count", return_value=2):
                result = {r["code"]: r for r in service._negative_feedback_for_day(session, target)}
            self.assertEqual(set(result), {"SH600001", "SH600003", "SH600006"})
            self.assertEqual(result["SH600003"]["category"], "former_leader")
            self.assertEqual(result["SH600003"]["recent_max_board"], 5)
            self.assertEqual(result["SH600006"]["category"], "recent_strong")
            self.assertEqual(result["SH600006"]["recent_max_board"], 3)
