import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import advancedFormat from "dayjs/plugin/advancedFormat";
import customParseFormat from "dayjs/plugin/customParseFormat";
import localeData from "dayjs/plugin/localeData";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";
import weekday from "dayjs/plugin/weekday";
import weekOfYear from "dayjs/plugin/weekOfYear";
import weekYear from "dayjs/plugin/weekYear";

dayjs.extend(customParseFormat);
dayjs.extend(advancedFormat);
dayjs.extend(weekday);
dayjs.extend(localeData);
dayjs.extend(weekOfYear);
dayjs.extend(weekYear);
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.locale("zh-cn");
dayjs.tz.setDefault("Asia/Shanghai");

/** 项目统一使用北京时间 */
export const BEIJING_TZ = "Asia/Shanghai";

/**
 * 解析后端时间戳（API UTC / 旧版 naive UTC / 旧版北京时间字符串）。
 */
export function parseApiTime(
  value: string | Date | dayjs.Dayjs | null | undefined
): dayjs.Dayjs {
  if (value == null || value === "") {
    return dayjs().tz(BEIJING_TZ);
  }
  if (dayjs.isDayjs(value)) {
    return value.tz(BEIJING_TZ);
  }
  const s = typeof value === "string" ? value.trim() : dayjs(value).toISOString();
  if (/Z$/i.test(s) || /[+-]\d{2}:\d{2}$/.test(s)) {
    return dayjs(s).tz(BEIJING_TZ);
  }
  // 旧版 manifest：YYYY-MM-DD HH:mm:ss（服务器本地北京时间）
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) {
    return dayjs.tz(s, "YYYY-MM-DD HH:mm:ss", BEIJING_TZ);
  }
  // ISO 无后缀：按 UTC naive 处理（旧版 API）
  return dayjs.utc(s).tz(BEIJING_TZ);
}

/** 当前北京时间 */
export function nowBeijing(): dayjs.Dayjs {
  return dayjs().tz(BEIJING_TZ);
}

/** 格式化为北京时间字符串 */
export function formatBeijingTime(
  value: string | null | undefined,
  format = "YYYY-MM-DD HH:mm:ss"
): string {
  if (!value) return "—";
  return parseApiTime(value).format(format);
}

/** 解析 YYYY-MM-DD 日历日期（按北京时间当天） */
export function parseBeijingDate(dateStr: string): dayjs.Dayjs {
  return dayjs.tz(dateStr, BEIJING_TZ);
}

export default dayjs;
