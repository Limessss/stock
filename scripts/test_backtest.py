"""端到端测试回测 API + WebSocket：
1. POST /api/backtest 启动一个小回测（只对已缓存的 5 只股票）
2. 同时打开 WebSocket /ws/backtest/{task_id}
3. 接收进度消息直到 done
4. GET /api/backtest/{task_id}/trades 拉成交记录
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

import websockets.sync.client as wsclient

BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"


def post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print("==> POST /api/backtest (max_codes=200, fast test)")
    r = post("/api/backtest", {
        "name": "smoke-test",
        "strategy": "breakout_washout",
        "params": {},
        "start_date": "2026-01-01",
        "end_date": "2026-05-28",
        "take_profit": 0.20,
        "stop_loss": 0.07,
        "max_hold": 20,
        "max_codes": 200,
    })
    task_id = r["task_id"]
    print(f"   task_id={task_id}  status={r['status']}")

    print(f"==> WS {WS_BASE}/ws/backtest/{task_id}")
    last_progress = None
    done = False
    error = None
    summary = None
    with wsclient.connect(f"{WS_BASE}/ws/backtest/{task_id}", open_timeout=10) as ws:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                raw = ws.recv(timeout=5)
            except TimeoutError:
                continue
            msg = json.loads(raw)
            t = msg.get("type")
            if t == "snapshot":
                print(f"   snapshot status={msg.get('status')}")
            elif t == "progress":
                if msg["done"] != last_progress:
                    last_progress = msg["done"]
                    print(f"   progress {msg['done']}/{msg['total']}  trades={msg['trade_count']}  "
                          f"elapsed={msg['elapsed_seconds']}s")
            elif t == "done":
                summary = msg.get("summary")
                print(f"   done  trades={msg['trade_count']}  elapsed={msg['elapsed_seconds']}s")
                done = True
                break
            elif t == "error":
                error = msg.get("error")
                print(f"   error  {error}")
                break
    if error:
        print("ERROR:", error)
        return 1
    if not done:
        print("ERROR: timeout waiting for done")
        return 1

    print(f"==> GET /api/backtest/{task_id}")
    task = get(f"/api/backtest/{task_id}")
    print(f"   status={task['status']}  trade_count={task['trade_count']}  "
          f"elapsed={task['elapsed_seconds']}s  summary={task['summary']}")

    print(f"==> GET /api/backtest/{task_id}/trades?page_size=5")
    page = get(f"/api/backtest/{task_id}/trades?page_size=5&sort_by=score")
    print(f"   total={page['total']}  rows={len(page['rows'])}")
    for tr in page["rows"]:
        print(f"     - {tr['code']} signal={tr['signal_date']} score={tr['score']:.2f}  "
              f"buy={tr['buy_date']}@{tr['buy_price']:.2f}  sell={tr['sell_date']}@{tr['sell_price']:.2f}  "
              f"ret={tr['return_pct']:+.2f}%  reason={tr['sell_reason']}")

    print()
    print("ALL OK  summary:", json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
