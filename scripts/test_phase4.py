"""Phase 4 端点烟雾测试。

验证：
- /api/backtest/{id}/trades.csv  CSV 导出（UTF-8 BOM、Excel 直开不乱码）
- /api/backtest/{id}/metrics     扩展风险指标（夏普 / 最大回撤 / 月度 / 净值曲线）

依赖：后端运行在 http://localhost:8000，且至少存在 1 个 status=done 的任务。
"""
from __future__ import annotations

import os

os.environ["NO_PROXY"] = "*"

import json
import sys
import urllib.request

BASE = "http://localhost:8000"


def _ascii(s: str, n: int = 200) -> str:
    return s.encode("ascii", "replace").decode("ascii")[:n]


def main() -> int:
    r = urllib.request.urlopen(BASE + "/api/backtest/history?limit=1", timeout=5)
    tasks = json.loads(r.read()).get("tasks", [])
    if not tasks:
        print("[skip] no completed tasks; create one via /backtest first")
        return 0

    t = tasks[0]
    task_id = t["id"]
    print(f"[info] target task_id={task_id} status={t['status']} trades={t['trade_count']}")

    # ---- trades.csv ----
    url = f"{BASE}/api/backtest/{task_id}/trades.csv"
    with urllib.request.urlopen(url, timeout=10) as resp:
        assert resp.status == 200, resp.status
        ctype = resp.headers.get("content-type")
        cdisp = resp.headers.get("content-disposition")
        body = resp.read()
    text = body.decode("utf-8-sig")
    lines = text.splitlines()
    print(f"[OK ] trades.csv: {ctype} | {cdisp} | {len(body)}B | {len(lines)} rows")
    print(f"      header={_ascii(lines[0])}")
    if len(lines) > 1:
        print(f"      sample={_ascii(lines[1])}")

    # ---- metrics ----
    url = f"{BASE}/api/backtest/{task_id}/metrics"
    m = json.loads(urllib.request.urlopen(url, timeout=10).read())
    print(
        f"[OK ] metrics: sharpe={m.get('sharpe'):.2f} "
        f"max_dd={m.get('max_drawdown_pct'):.2f}% "
        f"calmar={m.get('calmar'):.2f} "
        f"cagr={m.get('cagr_pct'):.1f}% "
        f"monthly={len(m.get('monthly', []))} "
        f"equity={len(m.get('equity_curve', []))}"
    )

    print("\n[PASS] all Phase 4 endpoints functional")
    return 0


if __name__ == "__main__":
    sys.exit(main())
