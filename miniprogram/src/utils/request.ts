import Taro from "@tarojs/taro";
import { API_BASE_URL, TOKEN_STORAGE_KEY, USER_STORAGE_KEY } from "../config";

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
type QueryValue = string | number | boolean | null | undefined;

type RequestOptions = {
  url: string;
  method?: HttpMethod;
  data?: unknown;
  params?: Record<string, QueryValue>;
  header?: Record<string, string>;
  skipAuthRedirect?: boolean;
};

export type CurrentUser = {
  id: number;
  username: string;
  full_name?: string | null;
  role: "member" | "manager" | "admin" | "superadmin" | string;
  is_active?: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: CurrentUser;
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

export function getToken() {
  return Taro.getStorageSync<string>(TOKEN_STORAGE_KEY);
}

export function setAuth(token: string, user: CurrentUser) {
  Taro.setStorageSync(TOKEN_STORAGE_KEY, token);
  Taro.setStorageSync(USER_STORAGE_KEY, user);
}

export function clearAuth() {
  Taro.removeStorageSync(TOKEN_STORAGE_KEY);
  Taro.removeStorageSync(USER_STORAGE_KEY);
}

export function getCurrentUser() {
  return Taro.getStorageSync<CurrentUser>(USER_STORAGE_KEY);
}

function redirectToLogin() {
  const pages = Taro.getCurrentPages();
  const currentRoute = pages[pages.length - 1]?.route || "";
  if (currentRoute !== "pages/profile/index") {
    Taro.navigateTo({ url: "/pages/profile/index" });
  }
}

// 小程序端统一请求封装：集中处理 API 地址、token、401/403 和网络错误。
export function request<T = unknown>({
  url,
  method = "GET",
  data,
  params,
  header,
  skipAuthRedirect = false,
}: RequestOptions): Promise<T> {
  const token = getToken();

  return new Promise((resolve, reject) => {
    Taro.request<T>({
      url: buildUrl(url, params),
      method,
      data,
      header: {
        "content-type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...header,
      },
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data);
          return;
        }

        const message = getErrorMessage(response.data, response.statusCode);
        if (response.statusCode === 401 && !skipAuthRedirect && !url.includes("/users/login")) {
          clearAuth();
          Taro.showToast({ title: "登录已过期，请重新登录", icon: "none" });
          redirectToLogin();
        } else if (response.statusCode === 403) {
          Taro.showToast({ title: "当前用户无权限", icon: "none" });
        }

        reject(new Error(message));
      },
      fail: (error) => {
        const message = error.errMsg || "网络异常，请检查后端服务";
        Taro.showToast({ title: message, icon: "none" });
        reject(new Error(message));
      },
    });
  });
}

export async function login(username: string, password: string) {
  const result = await request<LoginResponse>({
    url: "/users/login",
    method: "POST",
    data: { username, password },
    skipAuthRedirect: true,
  });
  setAuth(result.access_token, result.user);
  return result;
}

export { API_BASE_URL };
