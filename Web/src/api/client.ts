import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  timeout: 60_000,
});

/** 从 FastAPI / axios 错误中提取可读文案 */
export function formatApiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) {
            const loc = Array.isArray(item.loc) ? item.loc.join(".") : "";
            return loc ? `${loc}: ${item.msg}` : String(item.msg);
          }
          return JSON.stringify(item);
        })
        .join("；");
    }
    if (detail && typeof detail === "object") {
      return JSON.stringify(detail);
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const msg = formatApiError(err);
    console.error("[API error]", err?.response?.status, msg);
    return Promise.reject(new Error(msg));
  }
);
