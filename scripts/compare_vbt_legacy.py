"""比较 vbt 单笔 vs legacy 单笔 的成交结果。

用 smoke_test 的样本 + 几个真实命中 idx 直接对比。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from model.backtest.simulate_legacy import simulate_one as sim_legacy  # noqa: E402
from model.backtest.vbt_engine import simulate_codes_vbt  # noqa: E402
from model.data.cache import DataCache  # noqa: E402
from model.data.indicators import add_spread_column  # noqa: E402
from model.strategies import get_strategy  # noqa: E402

RAW = Path(r"C:\Users\66470\Desktop\stockmodel\data\raw")
CACHE = Path(r"C:\Users\66470\Desktop\stockmodel\data\cache")


def main() -> None:
    cache = DataCache(RAW, CACHE)
    strat = get_strategy("breakout_washout")

    # 选几只测试股票，跑同一时间窗口找 hits
    sample_codes = ["sz000001", "sz000002", "sz002281", "sz002552", "sz300939", "sz301217"]
    ts_s = pd.Timestamp("2026-01-01")
    ts_e = pd.Timestamp("2026-05-28")

    print(f"{'code':<10} {'idx':>5} {'date':<12}  legacy(ret/reason)  vbt(ret/reason)  match")
    print("-" * 100)

    legacy_total_ms = 0.0
    vbt_total_ms = 0.0
    n_tests = 0
    n_match = 0

    for code in sample_codes:
        df = cache.load_no_cache(code)
        if df is None:
            continue
        if "ma_spread_pct" not in df.columns:
            add_spread_column(df, inplace=True)
        mask = (df["date"] >= ts_s) & (df["date"] <= ts_e)
        if not mask.any():
            continue
        idxs = []
        for i in df.index[mask].tolist():
            if strat.scan(code, df, df.iloc[i]["date"], indicators_ready=True):
                idxs.append(int(i))
        if not idxs:
            continue

        # legacy
        t0 = time.perf_counter()
        legacy_results = [
            sim_legacy(df, i, take_profit=0.20, stop_loss=0.07, max_hold=20)
            for i in idxs
        ]
        legacy_total_ms += (time.perf_counter() - t0) * 1000

        # vbt batch
        t0 = time.perf_counter()
        vbt_results = simulate_codes_vbt(
            df, idxs, take_profit=0.20, stop_loss=0.07, max_hold=20
        )
        vbt_total_ms += (time.perf_counter() - t0) * 1000

        for i, lres, vres in zip(idxs, legacy_results, vbt_results):
            if not lres.executable:
                continue
            n_tests += 1
            ret_diff = abs(lres.return_pct - vres.return_pct)
            reason_match = (
                ("止盈" in lres.sell_reason and "止盈" in vres.sell_reason)
                or ("止损" in lres.sell_reason and "止损" in vres.sell_reason)
                or ("MA10" in lres.sell_reason and "MA10" in vres.sell_reason)
                or ("到期" in lres.sell_reason and "到期" in vres.sell_reason)
            )
            ok = ret_diff < 0.5 and reason_match
            if ok:
                n_match += 1
            print(f"{code:<10} {i:>5} {lres.buy_date:<12}  "
                  f"L:{lres.return_pct:+6.2f}% / {lres.sell_reason[:14]:<14}  "
                  f"V:{vres.return_pct:+6.2f}% / {vres.sell_reason[:14]:<14}  "
                  f"{'OK' if ok else 'DIFF'}")

    print("-" * 100)
    print(f"对比 {n_tests} 笔，匹配 {n_match} ({n_match/max(n_tests,1)*100:.1f}%)")
    print(f"耗时   legacy={legacy_total_ms:.1f}ms   vbt={vbt_total_ms:.1f}ms")


if __name__ == "__main__":
    main()
