/**
 * 策略参数中英文映射 + 描述。
 *
 * 字段维护策略：
 * - 中文 label 用于显示
 * - desc 用于 Tooltip 第二行（说明业务含义）
 * - 缺省 key 直接 fallback 显示原英文 key
 *
 * 当后端新增策略字段且未在此处登记时，前端不会报错——会显示原英文 key，
 * 提示开发者补登记即可。
 */

export interface ParamLabel {
  label: string;
  desc?: string;
}

const LABELS: Record<string, ParamLabel> = {
  // 历史窗口与横盘
  min_history: { label: "最少历史天数", desc: "需要至少多少根 K 线才尝试扫描" },
  consolidation_lookback: { label: "横盘回看窗口", desc: "判断前期横盘所看的天数" },
  max_range_pct: { label: "横盘最大振幅", desc: "前期横盘期最高/最低价振幅上限" },
  ma_spread_max_pct: { label: "均线粘合阈值", desc: "MA5/10/20/30/60 粘合度（极差/收盘价）上限" },
  require_consolidation: { label: "要求横盘", desc: "是否强制要求前期横盘形态" },
  require_pre_consolidation: { label: "要求洗盘前横盘", desc: "试盘高点之前是否要求横盘结构" },

  // 试盘高点搜索
  test_search_start: { label: "试盘搜索起点", desc: "从当前日往前第几日开始搜索试盘高点" },
  test_search_end: { label: "试盘搜索终点", desc: "搜索区间最远回看日数" },
  min_pullback_pct: { label: "最小回踩幅度", desc: "试盘高点 → 洗盘低点的回踩幅度下限" },
  max_pullback_pct: { label: "最大回踩幅度", desc: "回踩太深则视为破位，超过此幅度过滤" },
  min_test_vol_ratio: { label: "试盘最小量比", desc: "试盘高点当日成交量 / vol_ma20 下限" },
  max_pullback_vol_ratio: { label: "回踩最大量比", desc: "洗盘期均量 / 试盘日量上限（缩量回踩）" },
  quiet_days: { label: "缩量天数", desc: "回踩末段需保持缩量的最少天数" },

  // 突破当日
  min_breakout_pct: { label: "最小突破幅度", desc: "当日收盘 / 试盘高点 - 1 的下限" },
  breakout_vol_ratio: { label: "突破最小量比", desc: "突破日成交量 / vol_ma5 下限" },
  min_ma_bull_count: { label: "多头排列均线数", desc: "MA5/10/20/30/60 多头排列的最少根数（满分 5）" },
  macd_hist_min: { label: "MACD 柱下限", desc: "突破日 MACD 柱（DIF-DEA）的最小值" },
  close_above_ma20: { label: "收盘站上 MA20", desc: "要求当日收盘价高于 MA20" },
  require_yang_line: { label: "必须阳线", desc: "突破日必须收阳" },
  require_ma5_up: { label: "MA5 向上", desc: "突破日 MA5 上行" },
  require_positive_macd_hist: { label: "MACD 红柱", desc: "突破日 DIF-DEA > 0" },

  // 起爆位置过滤
  max_close_ma30_ratio: { label: "收盘 / MA30 上限", desc: "过滤已远离 MA30 的中段拉升票" },
  max_close_low60_ratio: { label: "收盘 / 60日低 上限", desc: "过滤距 60 日低点已涨幅过大的票" },
  max_close_over_washout: { label: "收盘 / 试盘高 上限", desc: "突破日收盘相对试盘高点的最大溢价" },

  // K 线形态
  min_day_change: { label: "最小当日涨幅", desc: "突破日 (close-prev_close)/prev_close 下限" },
  min_body_to_range: { label: "最小实体占比", desc: "实体长度 / 全长（K 线高低差）下限，过滤十字星" },
  max_upper_shadow_ratio: { label: "最大上影 / 实体", desc: "上影线 / 实体长度上限，过滤长上影" },

  // 胜率优先模式（方案 B）
  winrate_mode: { label: "胜率优先模式", desc: "启用更严的过滤组合，牺牲信号数换胜率" },
  wr_max_close_to_ma30: { label: "胜率·收盘 / MA30 上限" },
  wr_max_ma_spread_pct: { label: "胜率·均线粘合阈值" },
  wr_min_day_change: { label: "胜率·最小当日涨幅" },
  wr_max_day_change: { label: "胜率·最大当日涨幅", desc: "过滤涨停 / 暴量分歧" },
  wr_min_vol_ratio: { label: "胜率·最小量比" },
  wr_require_macd_positive: { label: "胜率·MACD 必须翻红" },
  // 起爆点策略
  min_wash_days: { label: "最少洗盘天数", desc: "试盘高点后最少洗盘交易日" },
  max_wash_days: { label: "最多洗盘天数", desc: "试盘高点后最多洗盘交易日" },
  min_break_pct: { label: "最小突破幅度", desc: "收盘相对试盘高点的最小溢价（比例）" },
  max_break_pct: { label: "最大突破幅度", desc: "普通分支：过滤过度延伸的突破日" },
  min_probe_gain: { label: "试盘最小涨幅", desc: "试盘高点相对基底低点的涨幅下限" },
  max_ma_spread: { label: "均线最大离散度", desc: "MA5/10/20/30/60 最大离散比例" },
  min_today_vol_ratio: { label: "当日最小量比", desc: "当日成交量 / 前20日均量下限" },
  release_lookback: { label: "放量释放回看", desc: "向前搜索放量释放日的天数" },
  min_release_vol_ratio: { label: "释放日最小量比", desc: "释放日成交量 / 其前20日均量下限" },
  min_release_high_to_test: { label: "释放日高点比例", desc: "释放日最高价须达到试盘高点的比例" },
  max_shrink_ratio: { label: "最大缩量比", desc: "洗盘末期均量 / 试盘期均量上限" },
  min_test_activity: { label: "试盘最小活跃度", desc: "试盘期均量 / 其前20日均量下限" },
  enable_strong_breakout: { label: "启用强势分支", desc: "是否启用短期强势突破分支" },
  strong_min_wash_days: { label: "强势·最少洗盘", desc: "强势分支最少洗盘天数" },
  strong_min_pct_chg: { label: "强势·最小涨幅", desc: "强势分支当日最小涨幅" },
  strong_min_break_pct: { label: "强势·最小突破", desc: "强势分支收盘高于试盘高点的比例" },
  strong_max_break_pct: { label: "强势·最大突破", desc: "强势分支最大突破幅度" },
  strong_min_vol_ratio: { label: "强势·最小量比", desc: "强势分支当日量比下限" },
  strong_max_ma_spread: { label: "强势·均线离散上限", desc: "强势分支允许的更大均线离散度" },
  strong_max_shrink_ratio: { label: "强势·最大缩量比", desc: "强势分支更宽松的缩量上限" },
  strong_min_close_pos: { label: "强势·收盘位置", desc: "强势分支收盘价在当日振幅中的位置下限" },
};

/** 类型字符串本地化（int/float/bool → 整数/小数/开关）。 */
const TYPE_LABELS: Record<string, string> = {
  int: "整数",
  float: "小数",
  bool: "开关",
  str: "文本",
};

export function getParamLabel(key: string): string {
  return LABELS[key]?.label ?? key;
}

export function getParamDesc(key: string): string | undefined {
  return LABELS[key]?.desc;
}

export function getTypeLabel(t: string): string {
  return TYPE_LABELS[t] ?? t;
}
