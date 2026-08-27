"""通过 HTTP 直接调用正在运行的后端，验证所有 Phase 2a 路由已生效。"""
from __future__ import annotations

import json
import urllib.request

BASE = "http://localhost:8000"


def get(path: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(BASE + path)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        try:
            return resp.status, json.loads(body)
        except json.JSONDecodeError:
            return resp.status, body


def post(path: str, data: dict) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body) if body else {}


def main() -> None:
    print("==> GET /api/health")
    s, b = get("/api/health")
    print(f"   {s}  cache_files={b['data']['cache_files']}")

    print("==> GET /api/strategies")
    s, b = get("/api/strategies")
    print(f"   {s}  strategies={[x['name'] for x in b['strategies']]}  "
          f"params={len(b['strategies'][0]['params_schema'])}")

    print("==> GET /api/data/stats")
    s, b = get("/api/data/stats")
    print(f"   {s}  {b}")

    print("==> POST /api/scan target_date=2026-04-09 limit=3")
    s, b = post("/api/scan", {
        "strategy": "breakout_washout",
        "params": {},
        "target_date": "2026-04-09",
        "limit": 3,
        "sort_by": "score",
        "desc": True,
    })
    print(f"   {s}  total={b['total']}  scanned={b['scanned']}  took_ms={b['took_ms']}")
    for row in b["rows"]:
        print(f"     - {row['code']} {row['date']} score={row['score']} breakout%={row['breakout_pct']}")

    print("==> GET /api/kline/SZ002281?last_n=60")
    s, b = get("/api/kline/SZ002281?last_n=60")
    print(f"   {s}  candles={len(b['candles'])}  ma60={len(b['ma60'])}")

    print()
    print("ALL ROUTES OK")


if __name__ == "__main__":
    main()
