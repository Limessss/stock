"""策略参数字段中文说明（供 LLM Prompt 使用）。"""
from __future__ import annotations

PARAM_LABELS: dict[str, dict[str, str]] = {
    "min_history": {"label": "最少历史天数", "desc": "需要至少多少根 K 线才尝试扫描"},
    "consolidation_lookback": {"label": "横盘回看窗口", "desc": "判断前期横盘所看的天数"},
    "max_range_pct": {"label": "横盘最大振幅", "desc": "前期横盘期最高/最低价振幅上限"},
    "ma_spread_max_pct": {"label": "均线粘合阈值", "desc": "MA 粘合度上限"},
    "min_pullback_pct": {"label": "最小回踩幅度", "desc": "试盘高点到洗盘低点的回踩幅度下限"},
    "max_pullback_pct": {"label": "最大回踩幅度", "desc": "回踩过深则过滤"},
    "min_breakout_pct": {"label": "最小突破幅度", "desc": "收盘相对试盘高点的突破下限"},
    "min_break_pct": {"label": "最小突破幅度", "desc": "收盘相对试盘高点的最小溢价"},
    "max_break_pct": {"label": "最大突破幅度", "desc": "过滤过度延伸的突破日"},
    "breakout_vol_ratio": {"label": "突破最小量比", "desc": "突破日成交量 / vol_ma5 下限"},
    "min_today_vol_ratio": {"label": "当日最小量比", "desc": "当日成交量 / 前20日均量下限"},
    "min_ma_bull_count": {"label": "多头排列均线数", "desc": "多头排列的最少根数"},
    "min_day_change": {"label": "最小当日涨幅", "desc": "当日涨幅下限"},
    "max_close_ma30_ratio": {"label": "收盘/MA30上限", "desc": "过滤远离 MA30 的票"},
    "max_close_over_washout": {"label": "收盘/试盘高上限", "desc": "突破日相对试盘高点的最大溢价"},
    "require_positive_macd_hist": {"label": "MACD红柱", "desc": "突破日 DIF-DEA > 0"},
    "winrate_mode": {"label": "胜率优先模式", "desc": "更严过滤换胜率"},
    "min_wash_days": {"label": "最少洗盘天数", "desc": "试盘后最少洗盘日"},
    "max_wash_days": {"label": "最多洗盘天数", "desc": "试盘后最多洗盘日"},
    "min_probe_gain": {"label": "试盘最小涨幅", "desc": "试盘高点相对基底低点涨幅下限"},
    "max_ma_spread": {"label": "均线最大离散度", "desc": "MA 最大离散比例"},
    "max_shrink_ratio": {"label": "最大缩量比", "desc": "洗盘末期均量 / 试盘期均量上限"},
    "enable_strong_breakout": {"label": "启用强势分支", "desc": "短期强势突破分支"},
}


def format_param_for_prompt(key: str, schema: dict) -> str:
    meta = PARAM_LABELS.get(key, {})
    label = meta.get("label", key)
    desc = meta.get("desc", "")
    default = schema.get("default")
    typ = schema.get("type", "")
    extra = f"; 说明：{desc}" if desc else ""
    return f"- {key}（{label}，类型 {typ}，默认 {default}{extra}）"
