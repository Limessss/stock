from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.app.services.interval_gain_service import get_interval_gains


class IntervalGainTests(unittest.TestCase):
    def test_interval_gain_ranking_and_disk_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            (cache_dir / "sh").mkdir()
            (cache_dir / "sz").mkdir()
            dates = pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"])
            pd.DataFrame({"trade_date": dates}).to_parquet(cache_dir / "market_overview.parquet", index=False)
            (cache_dir / "manifest.json").write_text("{}", encoding="utf-8")
            (cache_dir / "stock_names.json").write_text(
                json.dumps({"SH600001": "上涨股", "SZ000001": "下跌股"}, ensure_ascii=False),
                encoding="utf-8",
            )
            pd.DataFrame({
                "date": dates,
                # 模拟除权导致的原始价格断点；排行必须使用连续的 qfq_close。
                "close": [14.0, 15.4, 12.0, 15.0],
                "qfq_close": [10.0, 11.0, 12.0, 15.0],
            }).to_parquet(
                cache_dir / "sh" / "SH600001.parquet", index=False
            )
            pd.DataFrame({
                "date": dates,
                "close": [10.0, 9.0, 8.0, 7.0],
                "qfq_close": [10.0, 9.0, 8.0, 7.0],
            }).to_parquet(
                cache_dir / "sz" / "SZ000001.parquet", index=False
            )
            pd.DataFrame({
                "date": dates,
                "close": [5.0, 5.0, 5.0, 0.0],
                "qfq_close": [5.0, 5.0, 5.0, 0.0],
            }).to_parquet(
                cache_dir / "sh" / "SH600002.parquet", index=False
            )

            first = get_interval_gains(cache_dir, end_date="2026-08-06", days=2, limit=10)
            second = get_interval_gains(cache_dir, end_date="2026-08-06", days=2, limit=10)

            self.assertEqual(first["start_date"], "2026-08-04")
            self.assertEqual(first["end_date"], "2026-08-06")
            self.assertEqual([item["code"] for item in first["items"]], ["SH600001", "SZ000001"])
            self.assertEqual(first["scanned_stocks"], 2)
            self.assertAlmostEqual(first["items"][0]["gain_pct"], 36.3636)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["source"], "local_qfq_close_matrix")
            self.assertTrue(
                (cache_dir / "derived" / "interval_gains" / "close_matrix.parquet").exists()
            )

            selected = get_interval_gains(
                cache_dir,
                start_date="2026-08-03",
                end_date="2026-08-05",
                days=99,
                limit=10,
            )
            self.assertEqual(selected["start_date"], "2026-08-03")
            self.assertEqual(selected["end_date"], "2026-08-05")
            self.assertEqual(selected["days"], 2)
            self.assertAlmostEqual(selected["items"][0]["gain_pct"], 20.0)

    def test_default_period_uses_latest_ten_trading_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            (cache_dir / "sh").mkdir()
            (cache_dir / "sz").mkdir()
            dates = pd.bdate_range(end="2026-08-28", periods=12)
            # 故意让市场总览落后，默认区间仍应以个股行情的最新日期为准。
            pd.DataFrame({"trade_date": dates[:-2]}).to_parquet(
                cache_dir / "market_overview.parquet", index=False
            )
            (cache_dir / "manifest.json").write_text("{}", encoding="utf-8")
            (cache_dir / "stock_names.json").write_text(
                json.dumps({"SH600001": "有效股票"}, ensure_ascii=False),
                encoding="utf-8",
            )
            pd.DataFrame({
                "date": dates,
                "close": [10.0 + index for index in range(len(dates))],
                "qfq_close": [10.0 + index for index in range(len(dates))],
            }).to_parquet(cache_dir / "sh" / "SH600001.parquet", index=False)

            result = get_interval_gains(cache_dir, limit=10)

            self.assertEqual(result["start_date"], dates[-11].strftime("%Y-%m-%d"))
            self.assertEqual(result["end_date"], "2026-08-28")
            self.assertEqual(result["days"], 10)
            self.assertEqual(result["scanned_stocks"], 1)
            self.assertEqual([item["code"] for item in result["items"]], ["SH600001"])


if __name__ == "__main__":
    unittest.main()
