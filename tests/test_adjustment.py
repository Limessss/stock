from __future__ import annotations

import json

import pandas as pd

from model.data.adjustment import AdjustmentStore, adjustment_paths


def test_qfq_applies_event_only_before_ex_date(tmp_path):
    events_path, meta_path = adjustment_paths(tmp_path)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {
            "code": "SH603629",
            "ex_date": pd.Timestamp("2026-07-07"),
            "cash_dividend": 3.7,
            "rights_price": 0.0,
            "bonus_ratio": 4.0,
            "rights_ratio": 0.0,
        }
    ]).to_parquet(events_path, index=False)
    meta_path.write_text(json.dumps({"code_versions": {"SH603629": "v1"}}), encoding="utf-8")
    raw = pd.DataFrame([
        {"date": pd.Timestamp("2026-07-06"), "open": 171.19, "high": 174.78, "low": 165.0, "close": 172.90},
        {"date": pd.Timestamp("2026-07-07"), "open": 123.68, "high": 123.70, "low": 111.07, "close": 111.07},
    ])

    adjusted = AdjustmentStore(tmp_path).apply_qfq("SH603629", raw)

    assert adjusted.loc[0, "qfq_close"] == 123.24
    assert adjusted.loc[1, "qfq_open"] == 123.68
    assert adjusted.loc[1, "qfq_close"] == 111.07
    assert adjusted.loc[0, "close"] == 172.90


def test_future_event_does_not_adjust_latest_history(tmp_path):
    events_path, meta_path = adjustment_paths(tmp_path)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {
            "code": "SH600000",
            "ex_date": pd.Timestamp("2027-01-01"),
            "cash_dividend": 5.0,
            "rights_price": 0.0,
            "bonus_ratio": 5.0,
            "rights_ratio": 0.0,
        }
    ]).to_parquet(events_path, index=False)
    meta_path.write_text(json.dumps({"code_versions": {"SH600000": "v1"}}), encoding="utf-8")
    raw = pd.DataFrame([
        {"date": pd.Timestamp("2026-12-31"), "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0},
    ])

    adjusted = AdjustmentStore(tmp_path).apply_qfq("SH600000", raw)

    assert adjusted.loc[0, "qfq_close"] == 10.0
