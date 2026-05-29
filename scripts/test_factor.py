"""测试 /api/factor/analysis 端点。"""
from __future__ import annotations

import os
import sys

import requests

BASE = os.environ.get("BASE", "http://127.0.0.1:8004") + "/api"


def main(task_id: str) -> None:
    r = requests.get(
        f"{BASE}/factor/analysis",
        params={"task_id": task_id},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    print(f"total_trades: {data['total_trades']}")
    print()
    print("-- IC table (按 |ic_return| 降序) --")
    for row in data["ic"]:
        ic_r = row["ic_return"] or 0
        ic_u = row["ic_max_up"] or 0
        print(f"  {row['label']:<14}  ic_return={ic_r:+.4f}   ic_max_up={ic_u:+.4f}")
    print()
    for fac_name in ("score", "vol_ratio", "macd", "ma_spread_pct"):
        q = next((q for q in data["quantiles"] if q["field"] == fac_name), None)
        if q is None:
            continue
        print(f"-- 因子 {q['label']} 5 分位 --")
        for r in q["quantiles"]:
            print(
                f"  {r['quantile']}  N={r['count']:>4}  mean={r['mean']:+6.2f}%  "
                f"win={r['win_rate']:5.1f}%  big={r['big_win_rate']:4.1f}%"
            )
        print()


if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else "c2d82b2bf9bd"
    main(tid)
