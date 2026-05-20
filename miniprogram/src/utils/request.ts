import Taro from "@tarojs/taro";

export const API_BASE_URL = "http://127.0.0.1:8010";

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
type QueryValue = string | number | boolean | null | undefined;

type RequestOptions = {
  url: string;
  method?: HttpMethod;
  data?: unknown;
  params?: Record<string, QueryValue>;
  header?: Record<string, string>;
};

function buildUrl(url: string, params?: Record<string, QueryValue>) {
  if (!params) {
    return `${API_BASE_URL}${url}`;
  }

  const query = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join("&");

  if (!query) {
    return `${API_BASE_URL}${url}`;
  }

  const separator = url.includes("?") ? "&" : "?";
  return `${API_BASE_URL}${url}${separator}${query}`;
}

function getErrorMessage(data: unknown, statusCode: number) {
  if (typeof data === "object" && data !== null && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "object" && item !== null && "msg" in item) {
            return String((item as { msg?: unknown }).msg);
          }
          return String(item);
        })
        .join("；");
    }
  }
  return `请求失败：${statusCode}`;
}

// 小程序端统一请求封装，后续登录 token 可以在这里集中追加。
export function request<T = unknown>({
  url,
  method = "GET",
  data,
  params,
  header,
}: RequestOptions): Promise<T> {
  return new Promise((resolve, reject) => {
    Taro.request<T>({
      url: buildUrl(url, params),
      method,
      data,
      header: {
        "content-type": "application/json",
        ...header,
      },
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data);
          return;
        }

        reject(new Error(getErrorMessage(response.data, response.statusCode)));
      },
      fail: (error) => {
        reject(new Error(error.errMsg || "网络请求失败"));
      },
    });
  });
}
