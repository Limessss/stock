"""验证 name 字段已注入到所有 API。"""
import json, urllib.request

def get(path):
    with urllib.request.urlopen("http://localhost:8000" + path, timeout=60) as r:
        return json.loads(r.read())

def post(path, data):
    req = urllib.request.Request(
        "http://localhost:8000" + path,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

print("/api/health stock_names =", get("/api/health")["data"].get("stock_names"))

r = post("/api/scan", {
    "strategy": "breakout_washout", "params": {}, "target_date": "2026-04-09",
    "limit": 5, "max_codes": 200,
})
print(f"/api/scan: {r['total']} hits in {r['took_ms']}ms")
for row in r["rows"][:5]:
    print(f"  {row['code']:>10}  {row['name']:<12}  score={row['score']:.2f}")

d = get("/api/diagnose/SZ002281?date=2026-04-09")
print(f"/api/diagnose: code={d['code']} name={d['name']!r} score={d['score']}")

k = get("/api/kline/SZ002281?last_n=10")
print(f"/api/kline: code={k['code']} name={k['name']!r} candles={len(k['candles'])}")
