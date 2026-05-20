import axios from "axios";
import { message } from "antd";
import { clearAuthStorage } from "../auth/storage";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

// 后续登录模块完善后，可在这里统一附加 Authorization header。
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const requestUrl = String(error.config?.url || "");

    if (status === 401 && !requestUrl.includes("/users/login")) {
      clearAuthStorage();
      if (window.location.pathname !== "/login") {
        message.warning("登录已过期，请重新登录");
        window.location.href = "/login";
      }
    }

    if (status === 403) {
      message.error("当前用户无权限执行该操作");
    }

    return Promise.reject(error);
  },
);
