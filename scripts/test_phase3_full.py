"""Phase 3 全链路端到端：legacy / vectorbt 回测与指标。"""
from __future__ import annotations

import os
import time

import requests

BASE = os.environ.get("BASE", "http://127.0.0.1:8004") + "/api"


def create_and_wait(payload: dict, label: str) -> str:
    r = requests.post(f"{BASE}/backtest", json=payload, timeout=10)
    r.raise_for_status()
    tid = r.json()["task_id"]
    print(f"[{label}] task_id={tid}")
    t0 = time.time()
    while time.time() - t0 < 200:
        rs = requests.get(f"{BASE}/backtest/{tid}", timeout=5).json()
        if rs["status"] in ("done", "error"):
            print(f"[{label}] {rs['status']}  {rs.get('elapsed_seconds')}s  trades={rs['trade_count']}")
            print(f"[{label}] win_rate={rs['summary']['win_rate']:.2f}%  "
                  f"sharpe={rs['summary'].get('sharpe',0):.2f}  "
                  f"max_dd={rs['summary'].get('max_drawdown_pct',0):.2f}%")
            return tid
        time.sleep(1)
    raise TimeoutError(f"{label} timed out")


def main() -> None:
    base_payload = dict(
        name="phase3-full",
        strategy="breakout_washout",
        params={},
        start_date="2026-01-01",
        end_date="2026-05-28",
        take_profit=0.20,
        stop_loss=0.07,
        max_hold=20,
        split_tp=None,
        max_codes=200,
        num_workers=4,
    )

    # 1. legacy 引擎
    legacy_id = create_and_wait({**base_payload, "engine": "legacy"}, "legacy")

    # 2. vectorbt 引擎
    vbt_id = create_and_wait({**base_payload, "engine": "vectorbt"}, "vectorbt")

    # 3. /metrics 验证
    print("\n--- legacy /metrics ---")
    m = requests.get(f"{BASE}/backtest/{legacy_id}/metrics", timeout=10).json()
    print(f"  monthly={len(m['monthly'])} cells  equity={len(m['equity_curve'])} pts")

if __name__ == "__main__":
    main()
