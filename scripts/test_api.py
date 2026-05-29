"""用 TestClient 对新加的 API 做集成测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

c = TestClient(app)


def show(label: str, resp) -> None:
    print(f"--- {label} ---")
    print(f"  status={resp.status_code}")
    body = resp.json()
    s = json.dumps(body, ensure_ascii=False, default=str)
    if len(s) > 600:
        s = s[:600] + " ..."
    print(f"  body={s}")
    print()


print("1) GET /api/health")
show("health", c.get("/api/health"))

print("2) GET /api/strategies")
show("strategies", c.get("/api/strategies"))

print("3) GET /api/data/stats")
show("stats", c.get("/api/data/stats"))

print("4) POST /api/scan target_date=2026-04-09 limit=5")
resp = c.post("/api/scan", json={
    "strategy": "breakout_washout",
    "params": {},
    "target_date": "2026-04-09",
    "limit": 5,
    "sort_by": "score",
    "desc": True,
})
show("scan", resp)

print("5) GET /api/diagnose/SZ002281?date=2026-04-09")
show("diagnose", c.get("/api/diagnose/SZ002281?date=2026-04-09"))

print("6) GET /api/kline/SZ002281?last_n=60")
resp = c.get("/api/kline/SZ002281?last_n=60")
body = resp.json()
print(f"  status={resp.status_code}  candles={len(body.get('candles', []))}  "
      f"ma60_points={len(body.get('ma60', []))}")
