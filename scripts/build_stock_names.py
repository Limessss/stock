"""一次性拉取全市场 A 股代码 → 名称表，落到 data/cache/stock_names.json。

要联网。需要时重跑（每月一次即可）。

输出格式: {"SH600000": "浦发银行", "SZ000001": "平安银行", ...}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 禁用系统代理（Windows 下 requests 会自动读 IE 代理设置）
import os  # noqa: E402

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

import akshare as ak  # noqa: E402

from model.data.tdx_parser import is_a_share_code  # noqa: E402

OUT_PATH = Path(r"C:\Users\66470\Desktop\stockmodel\data\cache\stock_names.json")


def normalize_code(raw: str) -> str | None:
    """akshare 返回 '600000' / '000001'；我们 cache 用 'SH600000' / 'SZ000001'。"""
    raw = str(raw).strip().upper()
    if not raw.isdigit() or len(raw) != 6:
        return None
    if raw.startswith(("60", "68")):
        return f"SH{raw}"
    if raw.startswith(("00", "30")):
        return f"SZ{raw}"
    return None


def fetch_from_sse_szse() -> dict[str, str]:
    """从沪深交易所官方清单拉名称（最稳定）。

    akshare 内部：
      stock_info_sh_name_code 上交所主板/科创板
      stock_info_sz_name_code 深交所主板/创业板
      stock_info_bj_name_code 北交所（我们不收录）
    """
    name_map: dict[str, str] = {}

    # 上交所：主板 + 科创板
    for tab in ("主板A股", "科创板"):
        print(f"   上交所 {tab}...")
        try:
            df = ak.stock_info_sh_name_code(symbol=tab)
        except Exception as e:
            print(f"     失败: {e}")
            continue
        code_col = "证券代码" if "证券代码" in df.columns else df.columns[0]
        name_col = "证券简称" if "证券简称" in df.columns else df.columns[1]
        for _, r in df.iterrows():
            code = normalize_code(r[code_col])
            if not code or not is_a_share_code(code.lower()):
                continue
            name_map[code] = str(r[name_col]).strip()
        print(f"     +{len(df)} 行，累计 {len(name_map)}")

    # 深交所：A 股列表（主板 + 创业板）
    for tab in ("A股列表",):
        print(f"   深交所 {tab}...")
        try:
            df = ak.stock_info_sz_name_code(symbol=tab)
        except Exception as e:
            print(f"     失败: {e}")
            continue
        # 深交所表里 code 列名是 "A股代码"，name 列名是 "A股简称"
        candidates_code = ["A股代码", "证券代码", "代码"]
        candidates_name = ["A股简称", "证券简称", "名称"]
        code_col = next((c for c in candidates_code if c in df.columns), df.columns[0])
        name_col = next((c for c in candidates_name if c in df.columns), df.columns[1])
        for _, r in df.iterrows():
            code = normalize_code(r[code_col])
            if not code or not is_a_share_code(code.lower()):
                continue
            name_map[code] = str(r[name_col]).strip()
        print(f"     +{len(df)} 行，累计 {len(name_map)}")

    return name_map


def main() -> int:
    print("==> 从沪深交易所官方清单拉取名称")
    name_map = fetch_from_sse_szse()

    if not name_map:
        print("ERROR: 没有拉到任何名称")
        return 1

    # 合并 Parquet 缓存中有、但交易所清单未收录的代码（多为退市/旧代码）
    cache_dir = OUT_PATH.parent
    cache_codes: set[str] = set()
    for p in cache_dir.glob("*.parquet"):
        code = p.stem.upper()
        if is_a_share_code(code.lower()):
            cache_codes.add(code)
    missing = sorted(c for c in cache_codes if c not in name_map)
    if missing:
        print(f"==> 缓存中缺失名称 {len(missing)} 只，尝试东财补全…")
        from model.data.names import enrich_stock_names, set_names_file

        set_names_file(OUT_PATH)
        enriched = enrich_stock_names(missing, persist=False)
        added = 0
        for code, name in enriched.items():
            if name:
                name_map[code] = name
                added += 1
        print(f"   东财补全 {added}/{len(missing)} 只")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(name_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"==> 写入 {OUT_PATH}")
    print(f"   有效股票数: {len(name_map)}")
    print(f"   示例: {list(name_map.items())[:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
