from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.database import Base
from backend.app.models.market import MarketDailySummary
from backend.app.services import market_store
from model.data import a_stock_market


class MarketAmountTests(unittest.TestCase):
    def test_historical_amount_rejects_single_market_result(self) -> None:
        def index_bar(secid: str, _trade_date: str) -> dict | None:
            if secid == "1.000001":
                return {"amount": 944_307_568_640.0}
            return None

        with mock.patch.object(
            a_stock_market, "eastmoney_index_kline", side_effect=index_bar
        ):
            amount = a_stock_market.eastmoney_historical_amount("2026-09-01")

        self.assertIsNone(amount)

    def test_tdx_index_amount_requires_and_sums_both_markets(self) -> None:
        def parsed(path: Path) -> pd.DataFrame | None:
            amount = {
                "sh000001.day": 944_307_568_640.0,
                "sz399001.day": 1_089_095_270_400.0,
            }.get(path.name)
            if amount is None:
                return None
            return pd.DataFrame(
                {"date": pd.to_datetime(["2026-09-01"]), "amount": [amount]}
            )

        with mock.patch.object(a_stock_market, "parse_day_file", side_effect=parsed):
            amount = a_stock_market.tdx_index_amount_sum(
                "2026-09-01", Path("raw")
            )

        self.assertEqual(amount, 2_033_402_839_040.0)

    def test_detects_persisted_single_market_amount(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(
                MarketDailySummary(
                    trade_date="2026-09-01",
                    total_amount=944_307_561_356.8,
                )
            )
            session.commit()
            with (
                mock.patch.object(market_store, "is_after_market_close", return_value=True),
                mock.patch.object(
                    market_store,
                    "tdx_index_amount_sum",
                    return_value=2_033_402_839_040.0,
                ),
            ):
                self.assertTrue(
                    market_store.amount_needs_refresh(session, "2026-09-01")
                )


if __name__ == "__main__":
    unittest.main()
