"""端到端测试：通过 API 创建并行回测任务，等待完成，输出耗时和摘要 + metrics。"""
from __future__ import annotations

import os
import sys
import time

import requests

BASE = os.environ.get("BASE", "http://127.0.0.1:8002") + "/api"


def main() -> None:
    payload = {
        "name": "phase3a-parallel",
        "strategy": "breakout_washout",
        "params": {},
        "start_date": "2026-01-01",
        "end_date": "2026-05-28",
        "take_profit": 0.20,
        "stop_loss": 0.07,
        "max_hold": 20,
        "split_tp": None,
        "max_codes": 1500,
        "num_workers": 6,
    }
    print("POST /backtest", payload)
    r = requests.post(f"{BASE}/backtest", json=payload, timeout=10)
    r.raise_for_status()
    task_id = r.json()["task_id"]
    print(f"task_id={task_id}")

    t0 = time.time()
    last_log = 0.0
    while time.time() - t0 < 300:
        rs = requests.get(f"{BASE}/backtest/{task_id}", timeout=5).json()
        st = rs["status"]
        if time.time() - last_log >= 3:
            print(f"  [{rs['progress']}/{rs['total']}] status={st} trades={rs['trade_count']}")
            last_log = time.time()
        if st in ("done", "error", "cancelled"):
            print("--- 完成 ---")
            print(f"耗时 {rs.get('elapsed_seconds')}s   trades={rs['trade_count']}")
            sm = rs.get("summary") or {}
            print("summary 关键指标:")
            for k in ("win_rate", "avg_return", "sharpe", "max_drawdown_pct",
                     "calmar", "cagr_pct"):
                if k in sm:
                    print(f"  {k:20s} = {sm[k]:.4f}")
            if st == "done":
                m = requests.get(f"{BASE}/backtest/{task_id}/metrics", timeout=10).json()
                print(f"\nmetrics: sharpe={m['sharpe']:.2f}  max_dd={m['max_drawdown_pct']:.2f}%  "
                      f"calmar={m['calmar']:.2f}  cagr={m['cagr_pct']:.2f}%")
                print(f"  monthly cells: {len(m['monthly'])}  equity points: {len(m['equity_curve'])}")
                if m['monthly']:
                    print(f"  monthly head: {m['monthly'][:3]}")
            print(f"error  : {rs.get('error')}")
            sys.exit(0 if st == "done" else 1)
        time.sleep(0.8)
    print("超时")
    sys.exit(2)


if __name__ == "__main__":
    main()
