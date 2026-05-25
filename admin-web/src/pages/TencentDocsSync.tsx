import {
  Alert,
  Button,
  Card,
  Descriptions,
  InputNumber,
  Modal,
  Space,
  Table,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadProps } from "antd";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { formatBeijingTime } from "../utils/time";

type SyncStatus = {
  has_client_id: boolean;
  has_client_secret: boolean;
  has_redirect_uri: boolean;
  has_doc_id?: boolean;
  has_sheet_id?: boolean;
  has_token?: boolean;
  mock_enabled?: boolean;
  excel_enabled?: boolean;
  tencent_docs_enabled?: boolean;
  client_id_configured?: boolean;
  client_secret_configured?: boolean;
  redirect_uri_configured?: boolean;
  doc_id_configured?: boolean;
  token_saved?: boolean;
  mode: "mock" | "local" | "api" | "real";
  description?: string;
};

type TencentDocsRealStatus = {
  mode: "real" | "mock" | "local";
  auth_mode?: "oauth" | "direct_token";
  client_id_configured: boolean;
  client_secret_configured: boolean;
  redirect_uri_configured: boolean;
  access_token_configured?: boolean;
  doc_id_configured: boolean;
  doc_id?: string | null;
  encoded_id_configured?: boolean;
  encoded_id?: string | null;
  file_id_configured?: boolean;
  file_id_resolved?: boolean;
  file_id?: string | null;
  book_id_configured?: boolean;
  book_id_resolved?: boolean;
  book_id?: string | null;
  sheet_id_configured?: boolean;
  sheet_id_resolved?: boolean;
  sheet_id?: string | null;
  sheet_id_candidates?: SheetCandidate[];
  sheet_title_configured?: boolean;
  sheet_title?: string | null;
  sheet_range_configured?: boolean;
  sheet_range?: string | null;
  template_type?: string | null;
  active_month?: number | null;
  read_endpoint_enabled?: boolean;
  write_endpoint_enabled?: boolean;
  last_probe_error?: string | null;
  tab_id_configured?: boolean;
  tab_id?: string | null;
  default_year: number;
  ready_for_direct_token?: boolean;
  sheet_read_endpoint_configured?: boolean;
  sheet_write_endpoint_configured?: boolean;
  ready_for_api_endpoint?: boolean;
  ready_for_import?: boolean;
  ready_for_export?: boolean;
  token_saved: boolean;
  token_valid: boolean;
  token_expires_at?: string | null;
  token_expiry_source?: string | null;
  token_expiry_status?: "valid" | "expiring_soon" | "expired" | "unknown" | string | null;
  token_remaining_seconds?: number | null;
  token_remaining_text?: string | null;
  token_expiring_soon?: boolean;
  token_expiry_warning_threshold_days?: number;
  open_id_saved: boolean;
  ready_for_oauth: boolean;
  ready_for_sync: boolean;
};

type TencentDocsSheetsDebug = {
  success: boolean;
  file_id?: string;
  configured_sheet_id?: string;
  sheet_id_warning?: string | null;
  sheet_id_candidates?: SheetCandidate[];
  raw_response?: any;
};

type SheetCandidate = {
  sheetId?: string;
  id?: string;
  title?: string;
  name?: string;
  rowCount?: number | null;
  columnCount?: number | null;
  raw?: Record<string, string>;
};

type SyncLog = {
  id: number;
  source: string;
  sync_type: string;
  status: string;
  message?: string;
  detail_json?: string;
  created_at: string;
};

type ImportErrorItem = {
  sheet?: string | null;
  row?: number | null;
  reagent?: string | null;
  reason: string;
};

type FileImportResult = {
  success: boolean;
  message: string;
  created: number;
  skipped: number;
  failed: number;
  created_count?: number;
  imported_count?: number;
  skipped_count?: number;
  failed_count?: number;
  errors: ImportErrorItem[];
  log_id: number;
  created_reagents?: number;
  updated_reagents?: number;
  raw_rows_count?: number;
  parsed_records_count?: number;
  invalid_records_preview?: ImportErrorItem[];
  parsed_records_preview?: any[];
};

function shouldShowImportError(error: ImportErrorItem) {
  const reason = error.reason || "";
  return !reason.includes("操作人不能为空") && !reason.includes("库存不足");
}

function getImportCounts(result: Partial<FileImportResult>) {
  const created = result.created_count ?? result.imported_count ?? result.created ?? 0;
  const skipped = result.skipped_count ?? result.skipped ?? 0;
  const failed = result.failed_count ?? result.failed ?? 0;
  return { created, skipped, failed };
}

function formatImportSummary(result: Partial<FileImportResult>) {
  const { created, skipped, failed } = getImportCounts(result);
  return `新增 ${created} 条，跳过 ${skipped} 条，失败 ${failed} 条`;
}

function expirySourceLabel(source?: string | null) {
  if (source === "database") return "数据库";
  if (source === "env") return "环境变量";
  return "";
}

function expiryStatusText(statusValue?: string | null) {
  if (statusValue === "valid") return "有效";
  if (statusValue === "expiring_soon") return "即将过期";
  if (statusValue === "expired") return "已过期";
  return "未设置";
}

function expiryStatusColor(statusValue?: string | null) {
  if (statusValue === "valid") return "#16a34a";
  if (statusValue === "expiring_soon") return "#d97706";
  if (statusValue === "expired") return "#dc2626";
  return "#64748b";
}

function toDateTimeLocalValue(value?: string | null) {
  if (!value) return "";
  const text = value.replace(" ", "T");
  if (!/[zZ]|[+-]\d{2}:\d{2}$/.test(text)) {
    return text.slice(0, 19);
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value || "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}:${get("second")}`;
}

function toBeijingOffsetIso(value: string) {
  return `${value.replace(" ", "T").slice(0, 19)}+08:00`;
}

function getApiErrorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (!detail) {
    return fallback;
  }
  if (typeof detail === "string") {
    if (detail.includes("status_code=404")) {
      return `腾讯文档 API 路径不正确或当前应用无权限，请检查 sheetbook API endpoint、bookID 和权限范围。${detail}`;
    }
    return detail;
  }
  const statusCode = detail?.diagnosis?.status_code ?? detail?.status_code;
  const messageText = detail.message || fallback;
  if (statusCode === 404 || String(messageText).includes("status_code=404")) {
    return `腾讯文档 API 路径不正确或当前应用无权限，请检查 sheetbook API endpoint、bookID 和权限范围。${messageText}`;
  }
  if (String(messageText).includes("bookID") || String(messageText).includes("TENCENT_DOCS_BOOK_ID")) {
    return "腾讯文档在线表格需要 bookID，请在后端环境变量中配置 TENCENT_DOCS_BOOK_ID，或先通过 OpenAPI 查询/转换获得。";
  }
  if (String(messageText).includes("sheetId") || String(messageText).includes("SHEET_ID")) {
    return "腾讯文档在线表格需要 sheetID，请配置 TENCENT_DOCS_SHEET_ID，或配置 TENCENT_DOCS_SHEET_TITLE 让后端自动匹配。";
  }
  if (String(messageText).includes("fileID") || String(messageText).includes("ENCODED_ID")) {
    return "腾讯文档需要先解析官方 fileID，请配置 TENCENT_DOCS_ENCODED_ID 或官方 TENCENT_DOCS_FILE_ID，并确认 Direct Token 有权限调用 converter。";
  }
  return detail.message || fallback;
}

export default function TencentDocsSync() {
  const { hasRole } = useAuth();
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [realStatus, setRealStatus] = useState<TencentDocsRealStatus | null>(null);
  const [logs, setLogs] = useState<SyncLog[]>([]);
  const [exportYear, setExportYear] = useState<number>(2026);
  const [activeMonth, setActiveMonth] = useState<number>(1);
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [realSyncLoading, setRealSyncLoading] = useState(false);
  const [sheetsDebugLoading, setSheetsDebugLoading] = useState(false);
  const [matrixDebugLoading, setMatrixDebugLoading] = useState(false);
  const [writeCellLoading, setWriteCellLoading] = useState(false);
  const [sheetsDebug, setSheetsDebug] = useState<TencentDocsSheetsDebug | null>(null);
  const [importDryRunResult, setImportDryRunResult] = useState<any | null>(null);
  const [exportPreviewResult, setExportPreviewResult] = useState<any | null>(null);
  const [writeCellResult, setWriteCellResult] = useState<any | null>(null);
  const [tokenExpiryModalOpen, setTokenExpiryModalOpen] = useState(false);
  const [tokenExpiryInput, setTokenExpiryInput] = useState("");
  const [tokenExpirySaving, setTokenExpirySaving] = useState(false);
  const [errors, setErrors] = useState<ImportErrorItem[]>([]);
  const [errorModalOpen, setErrorModalOpen] = useState(false);
  const [lastImportResult, setLastImportResult] = useState<FileImportResult | null>(null);
  // 正式导入/同步弹窗状态
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importModalYear, setImportModalYear] = useState<number>(2026);
  const [importModalMonth, setImportModalMonth] = useState<number>(1);
  const [importModalMode, setImportModalMode] = useState<"single" | "all">("single");
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportModalYear, setExportModalYear] = useState<number>(2026);
  const [exportModalMonth, setExportModalMonth] = useState<number>(1);
  const [exportModalMode, setExportModalMode] = useState<"single" | "all">("single");
  const [allMonthsResult, setAllMonthsResult] = useState<any | null>(null);
  const canOperateSync = hasRole("admin", "superadmin");
  const showMockButtons = canOperateSync && status?.mock_enabled !== false;

  // localStorage helpers
  const lsGet = (key: string, fallback: any) => {
    try {
      const raw = localStorage.getItem(key);
      return raw !== null ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  };
  const lsSet = (key: string, value: any) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch { /* ignore */ }
  };

  const loadData = () => {
    Promise.all([
      apiClient.get<SyncStatus>("/api/sync/status"),
      apiClient.get<TencentDocsRealStatus>("/api/tencent-docs/status"),
      apiClient.get<SyncLog[]>("/api/sync/logs"),
    ])
      .then(([statusResponse, realStatusResponse, logsResponse]) => {
        setStatus(statusResponse.data);
        setRealStatus(realStatusResponse.data);
        if (realStatusResponse.data.active_month) {
          setActiveMonth(realStatusResponse.data.active_month);
        }
        // Restore modal defaults from localStorage
        const now = new Date();
        const defaultYear = realStatusResponse.data.default_year || now.getFullYear();
        const defaultMonth = now.getMonth() + 1;
        setImportModalYear(lsGet("tencentDocsLastImportYear", defaultYear));
        setImportModalMonth(lsGet("tencentDocsLastImportMonth", defaultMonth));
        setImportModalMode(lsGet("tencentDocsLastImportMode", "single"));
        setExportModalYear(lsGet("tencentDocsLastExportYear", defaultYear));
        setExportModalMonth(lsGet("tencentDocsLastExportMonth", defaultMonth));
        setExportModalMode(lsGet("tencentDocsLastExportMode", "single"));
        setLogs(logsResponse.data);
      })
      .catch(() => message.warning("同步状态加载失败"));
  };

  useEffect(() => {
    loadData();
  }, []);

  const runMockImport = () => {
    apiClient
      .post<FileImportResult>("/api/sync/mock/import")
      .then((response) => {
        setLastImportResult(response.data);
        message.success(response.data.message || `mock 导入完成：${formatImportSummary(response.data)}`);
        loadData();
      })
      .catch(() => message.error("mock 导入失败"));
  };

  const runMockExport = () => {
    apiClient
      .post("/api/sync/mock/export")
      .then(() => {
        message.success("mock 导出完成");
        loadData();
      })
      .catch(() => message.error("mock 导出失败"));
  };

  const uploadSyncFile = async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    setUploading(true);
    try {
      const response = await apiClient.post<FileImportResult>("/api/sync/excel/import", formData, {
        timeout: 120000,
      });
      const result = response.data;
      setLastImportResult(result);
      message.success(result.message || `文件导入完成：${formatImportSummary(result)}`);
      const visibleErrors = (result.errors || []).filter(shouldShowImportError);
      setErrors(visibleErrors);
      if (visibleErrors.length) {
        setErrorModalOpen(true);
      }
      loadData();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "文件导入失败");
    } finally {
      setUploading(false);
    }
  };

  const uploadProps: UploadProps = {
    accept: ".xlsx,.xls,.csv",
    showUploadList: false,
    beforeUpload(file) {
      void uploadSyncFile(file);
      return Upload.LIST_IGNORE;
    },
  };

  const downloadExportFile = async () => {
    setExporting(true);
    try {
      const response = await apiClient.get<Blob>("/api/sync/excel/export", {
        params: { year: exportYear },
        responseType: "blob",
        timeout: 120000,
      });
      const url = window.URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `excel_inventory_${exportYear}_${Date.now()}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      message.success("Excel 导出完成");
      loadData();
    } catch {
      message.error("导出 Excel 失败");
    } finally {
      setExporting(false);
    }
  };

  const authorizeTencentDocs = async () => {
    if (!realStatus?.ready_for_oauth) {
      message.warning("请先在后端 .env 中配置 Client ID、Client Secret 和 Redirect URI");
      return;
    }

    setRealSyncLoading(true);
    try {
      const response = await apiClient.get<{ oauth_url: string }>("/api/tencent-docs/oauth-url");
      window.location.href = response.data.oauth_url;
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "生成腾讯文档授权地址失败");
    } finally {
      setRealSyncLoading(false);
    }
  };

  const refreshTencentDocsStatus = async () => {
    setRealSyncLoading(true);
    try {
      const response = await apiClient.post<TencentDocsRealStatus>("/api/tencent-docs/refresh-status");
      setRealStatus(response.data);
      message.success("腾讯文档授权状态已刷新");
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "刷新腾讯文档授权状态失败");
    } finally {
      setRealSyncLoading(false);
    }
  };

  const loadTencentDocsSheetsDebug = async () => {
    setSheetsDebugLoading(true);
    try {
      const response = await apiClient.get<TencentDocsSheetsDebug>("/api/tencent-docs/sheets");
      setSheetsDebug(response.data);
      message.success("腾讯文档 sheet 信息已获取");
    } catch (error: any) {
      message.error(getApiErrorMessage(error, "获取腾讯文档 sheet 信息失败"));
    } finally {
      setSheetsDebugLoading(false);
    }
  };

  const runTencentDocsImportDryRun = async () => {
    setMatrixDebugLoading(true);
    try {
      const response = await apiClient.post("/api/tencent-docs/debug/import-dry-run", null, {
        params: { year: exportYear, month: activeMonth },
        timeout: 120000,
      });
      setImportDryRunResult(response.data);
      message.success("导入预检完成");
    } catch (error: any) {
      message.error(getApiErrorMessage(error, "腾讯文档导入预检失败"));
    } finally {
      setMatrixDebugLoading(false);
    }
  };

  const runTencentDocsExportPreview = async () => {
    setMatrixDebugLoading(true);
    try {
      const response = await apiClient.get("/api/tencent-docs/debug/export-preview", {
        params: { year: exportYear, month: activeMonth },
        timeout: 120000,
      });
      setExportPreviewResult(response.data);
      message.success("导出预览完成");
    } catch (error: any) {
      message.error(getApiErrorMessage(error, "腾讯文档导出预览失败"));
    } finally {
      setMatrixDebugLoading(false);
    }
  };

  const runWriteCellTest = async () => {
    setWriteCellLoading(true);
    try {
      const response = await apiClient.post("/api/tencent-docs/debug/write-cell", null, {
        params: { year: exportYear, month: activeMonth },
        timeout: 120000,
      });
      setWriteCellResult(response.data);
      if (response.data.any_success) {
        message.success("Write-Cell 测试成功：请打开腾讯文档第一个 sheet，查看左上角 A1 单元格是否出现测试值。");
      } else {
        message.warning("Write-Cell 测试失败：请检查 bookID、Direct Token 和 000001 sheet 权限。");
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, "Write-Cell 测试失败"));
    } finally {
      setWriteCellLoading(false);
    }
  };

  const importFromTencentDocs = async () => {
    // 打开弹窗选择单月/全年，不再直接使用页面月份
    setImportModalOpen(true);
  };

  // ── Job polling helper ──────────────────────────────────────────
  const pollJob = async (
    jobId: string,
    jobType: string,
    onDone: (result: any) => void,
  ) => {
    const maxAttempts = 200;
    const intervalMs = 2000;
    let attempts = 0;
    let consecutiveFailures = 0;
    const poll = async () => {
      attempts++;
      try {
        const resp = await apiClient.get(`/api/tencent-docs/jobs/${jobId}`, { timeout: 10000 });
        consecutiveFailures = 0;
        const j = resp.data as any;
        // Update progress
        if (j.status === "running") {
          message.loading({ content: j.message || `${jobType} 执行中…`, key: jobId, duration: 0 });
        }
        if (j.status === "success" || j.status === "partial_success") {
          message.destroy(jobId);
          message.success(j.message || `${jobType}完成`);
          if (j.result) {
            if (j.result.per_month_results) setAllMonthsResult(j.result);
            else setAllMonthsResult(j.result);
          }
          onDone(j.result);
          loadData();
          return;
        }
        if (j.status === "failed") {
          message.destroy(jobId);
          message.error(`任务执行失败：${j.error_message || j.message || "未知错误"}`);
          return;
        }
        if (["no_data", "no_new_data", "no_matched_records"].includes(j.status)) {
          message.destroy(jobId);
          message.info(j.message || "当前没有需要同步的数据");
          onDone(j.result);
          loadData();
          return;
        }
        if (attempts >= maxAttempts) {
          message.destroy(jobId);
          message.warning("任务超时，可能仍在后台执行，请稍后刷新同步日志确认结果");
          return;
        }
      } catch {
        consecutiveFailures++;
        if (consecutiveFailures >= 3) {
          message.destroy(jobId);
          message.warning("暂时无法获取任务状态，任务可能仍在后台执行，请稍后刷新同步日志确认结果");
          return;
        }
      }
      setTimeout(poll, intervalMs);
    };
    poll();
  };

  const confirmImport = async () => {
    setImportModalOpen(false);
    const isAll = importModalMode === "all";
    lsSet("tencentDocsLastImportYear", importModalYear);
    lsSet("tencentDocsLastImportMonth", importModalMonth);
    lsSet("tencentDocsLastImportMode", importModalMode);
    try {
      const payload: any = { year: importModalYear, all_months: isAll };
      if (!isAll) payload.month = importModalMonth;
      const resp = await apiClient.post("/api/tencent-docs/import-jobs", payload, { timeout: 15000 });
      const data = resp.data as any;
      message.success(data.message || "导入任务已创建，正在后台执行");
      if (data.job_id) {
        pollJob(data.job_id, "导入", () => {});
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, "导入任务创建失败，请检查后端服务"));
    }
  };

  const exportToTencentDocs = async () => {
    setExportModalOpen(true);
  };

  const confirmExport = async () => {
    setExportModalOpen(false);
    const isAll = exportModalMode === "all";
    lsSet("tencentDocsLastExportYear", exportModalYear);
    lsSet("tencentDocsLastExportMonth", exportModalMonth);
    lsSet("tencentDocsLastExportMode", exportModalMode);
    try {
      const payload: any = { year: exportModalYear, all_months: isAll };
      if (!isAll) payload.month = exportModalMonth;
      const resp = await apiClient.post("/api/tencent-docs/export-jobs", payload, { timeout: 15000 });
      const data = resp.data as any;
      message.success(data.message || "同步任务已创建，正在后台执行");
      if (data.job_id) {
        pollJob(data.job_id, "同步", () => {});
      }
    } catch (error: any) {
      message.error(getApiErrorMessage(error, "同步任务创建失败，请检查后端服务"));
    }
  };

  const openTokenExpiryModal = () => {
    setTokenExpiryInput(toDateTimeLocalValue(realStatus?.token_expires_at));
    setTokenExpiryModalOpen(true);
  };

  const saveTokenExpiry = async (clear = false) => {
    if (!clear && !tokenExpiryInput) {
      message.warning("请选择 token 过期时间");
      return;
    }
    setTokenExpirySaving(true);
    try {
      await apiClient.put("/api/tencent-docs/token-expiry", {
        token_expires_at: clear ? null : toBeijingOffsetIso(tokenExpiryInput),
      });
      message.success(clear ? "Token 有效期已清除" : "Token 有效期已更新");
      setTokenExpiryModalOpen(false);
      loadData();
    } catch (error: any) {
      message.error(getApiErrorMessage(error, "Token 有效期更新失败"));
    } finally {
      setTokenExpirySaving(false);
    }
  };

  const renderConfigured = (value?: boolean) => (value ? "已配置" : "未配置");
  const renderSaved = (value?: boolean) => (value ? "已保存" : "未保存");
  const tokenStatusText = !realStatus?.token_saved ? "未授权" : expiryStatusText(realStatus.token_expiry_status);
  const missingTencentDocsItems = [
    !realStatus?.ready_for_direct_token ? "Direct Token 凭证" : null,
    !realStatus?.file_id_resolved ? "官方 fileID" : null,
    !realStatus?.book_id_resolved ? "bookID" : null,
    !realStatus?.sheet_id_resolved ? "sheetID" : null,
    !realStatus?.sheet_range_configured ? "读取/写入范围" : null,
  ].filter(Boolean);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        腾讯文档同步
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        message="本地文件同步模式"
        description={
          status?.description ||
          "当前为本地/模拟同步模式，可使用 Excel/CSV 导入导出；真实腾讯文档同步需完成授权配置后启用。"
        }
      />
      {status?.mode === "local" || status?.mode === "mock" ? (
        <Alert
          type="success"
          showIcon
          message="当前为模拟/本地同步模式，可测试导入导出流程；不会访问真实腾讯文档。"
        />
      ) : null}

      <Card size="small" title="同步操作">
        <Space wrap>
          {canOperateSync ? (
            <>
              <Button
                onClick={authorizeTencentDocs}
                disabled={!realStatus?.ready_for_oauth}
                loading={realSyncLoading}
              >
                授权腾讯文档
              </Button>
              <Button onClick={refreshTencentDocsStatus} loading={realSyncLoading}>
                刷新授权状态
              </Button>
              <Button onClick={loadTencentDocsSheetsDebug} loading={sheetsDebugLoading}>
                探测 Sheet 列表
              </Button>
              <Button onClick={runTencentDocsImportDryRun} loading={matrixDebugLoading}>
                导入预检
              </Button>
              <Button onClick={runTencentDocsExportPreview} loading={matrixDebugLoading}>
                导出预览
              </Button>
              <Button onClick={runWriteCellTest} loading={writeCellLoading}>
                Write-Cell 测试
              </Button>
              <Button
                onClick={importFromTencentDocs}
                disabled={!realStatus?.ready_for_import}
                loading={realSyncLoading}
              >
                从腾讯文档导入
              </Button>
              <Button
                onClick={exportToTencentDocs}
                disabled={!realStatus?.ready_for_export}
                loading={realSyncLoading}
              >
                同步到腾讯文档
              </Button>
              {showMockButtons ? (
                <>
                  <Button type="primary" onClick={runMockImport}>
                    Mock 导入
                  </Button>
                  <Button onClick={runMockExport}>Mock 导出</Button>
                </>
              ) : null}
              <Upload {...uploadProps}>
                <Button loading={uploading}>导入 Excel/CSV</Button>
              </Upload>
              <InputNumber
                min={2000}
                max={2100}
                value={exportYear}
                onChange={(value) => setExportYear(value || 2026)}
                addonBefore="年份"
                style={{ width: 150 }}
              />
              <InputNumber
                min={1}
                max={12}
                value={activeMonth}
                onChange={(value) => setActiveMonth(value || 1)}
                addonBefore="月份"
                style={{ width: 130 }}
              />
              <Button onClick={downloadExportFile} loading={exporting}>
                导出 Excel
              </Button>
            </>
          ) : (
            <Typography.Text type="secondary">当前角色仅可查看同步状态和日志</Typography.Text>
          )}
        </Space>
        <Typography.Paragraph
          type="secondary"
          style={{ fontSize: 13, marginTop: 14, marginBottom: 0, lineHeight: 1.65 }}
        >
          详见上方同步配置情况，如果授权模式是 Direct Token，则无需进行授权操作，只需要定期更新过期的令牌即可。只有采用 OAuth 授权模式时才需要授权，但是目前不推荐这种方式，腾讯文档官方似乎也没给出该模式接口（也可能是我没找到），默认 Direct Token，更多设置和维护请联系前后端维护管理员：
          <Typography.Link href="mailto:neuyh2023@163.com">neuyh2023@163.com</Typography.Link>
        </Typography.Paragraph>
      </Card>

      <Card size="small" title="同步状态">
        <Descriptions size="small" column={3}>
          <Descriptions.Item label="模式">{status?.mode ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="Mock 同步">{status?.mock_enabled === false ? "已关闭" : "已开启"}</Descriptions.Item>
          <Descriptions.Item label="Excel/CSV">{status?.excel_enabled === false ? "已关闭" : "已开启"}</Descriptions.Item>
          <Descriptions.Item label="client_id（腾讯应用 ID）">
            {(status?.client_id_configured ?? status?.has_client_id) ? "已配置" : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="client_secret（后端应用密钥）">
            {(status?.client_secret_configured ?? status?.has_client_secret) ? "已配置" : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="redirect_uri（OAuth 回调）">
            {(status?.redirect_uri_configured ?? status?.has_redirect_uri) ? "已配置" : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="doc_id（目标腾讯文档）">
            {(status?.doc_id_configured ?? status?.has_doc_id) ? "已配置" : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="token（授权状态）">
            {(status?.token_saved ?? status?.has_token) ? "已保存" : "未保存"}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card size="small" title="腾讯文档真实同步配置">
        <Descriptions size="small" column={3}>
          <Descriptions.Item label="模式">{realStatus?.mode ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="授权模式">
            {realStatus?.auth_mode === "direct_token" ? "Direct Token" : "OAuth"}
          </Descriptions.Item>
          <Descriptions.Item label="client_id">{renderConfigured(realStatus?.client_id_configured)}</Descriptions.Item>
          <Descriptions.Item label="access_token">{renderConfigured(realStatus?.access_token_configured)}</Descriptions.Item>
          <Descriptions.Item label="client_secret">
            {realStatus?.auth_mode === "direct_token" && !realStatus.client_secret_configured
              ? "Direct Token 模式可不填"
              : renderConfigured(realStatus?.client_secret_configured)}
          </Descriptions.Item>
          <Descriptions.Item label="redirect_uri">{renderConfigured(realStatus?.redirect_uri_configured)}</Descriptions.Item>
          <Descriptions.Item label="doc_id">{realStatus?.doc_id_configured ? realStatus.doc_id : "未配置"}</Descriptions.Item>
          <Descriptions.Item label="encoded_id">
            {realStatus?.encoded_id_configured ? realStatus.encoded_id || "已配置" : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="file_id">
            {realStatus?.file_id_resolved
              ? realStatus.file_id || "已解析"
              : realStatus?.file_id_configured
                ? "已配置，待解析"
                : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="bookID">
            {realStatus?.book_id_resolved
              ? realStatus.book_id || "已解析"
              : realStatus?.book_id_configured
                ? "已配置，待解析"
                : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="sheetID（旧/调试）">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {realStatus?.sheet_id
                ? `${realStatus.sheet_id}（仅调试/legacy，正式同步自动解析）`
                : "未配置（正式同步自动解析）"}
            </Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="sheet 标题">
            {realStatus?.sheet_title ? realStatus.sheet_title : realStatus?.sheet_title_configured ? "已配置" : "-"}
          </Descriptions.Item>
          <Descriptions.Item label="tab_id">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {realStatus?.tab_id_configured ? `${realStatus.tab_id || "已配置"}（旧字段，不用于正式同步）` : "未配置"}
            </Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="token">{renderSaved(realStatus?.token_saved)}</Descriptions.Item>
          <Descriptions.Item label="token 状态">
            <Typography.Text style={{ color: expiryStatusColor(realStatus?.token_expiry_status), fontWeight: 600 }}>
              {tokenStatusText}
            </Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="token 过期时间">
            <Space size={8}>
              <Typography.Text>{formatBeijingTime(realStatus?.token_expires_at)}</Typography.Text>
              {canOperateSync ? (
                <Button size="small" onClick={openTokenExpiryModal}>
                  更新令牌有效期
                </Button>
              ) : null}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="剩余有效期">
            {realStatus?.token_remaining_text || "-"}
          </Descriptions.Item>
          <Descriptions.Item label="过期提醒">
            <Typography.Text style={{ color: expiryStatusColor(realStatus?.token_expiry_status), fontWeight: 600 }}>
              {expiryStatusText(realStatus?.token_expiry_status)}
            </Typography.Text>
            {expirySourceLabel(realStatus?.token_expiry_source) ? (
              <Typography.Text type="secondary">（{expirySourceLabel(realStatus?.token_expiry_source)}）</Typography.Text>
            ) : null}
          </Descriptions.Item>
          <Descriptions.Item label="open_id">{realStatus?.open_id_saved ? "已获取" : "未获取"}</Descriptions.Item>
          <Descriptions.Item label="OAuth 条件">{realStatus?.ready_for_oauth ? "已满足" : "缺少配置"}</Descriptions.Item>
          <Descriptions.Item label="Direct Token 条件">
            {realStatus?.ready_for_direct_token ? "已满足" : "缺少配置"}
          </Descriptions.Item>
          <Descriptions.Item label="sheet range">
            {realStatus?.sheet_range_configured ? realStatus.sheet_range || "已配置" : "未配置"}
          </Descriptions.Item>
          <Descriptions.Item label="读取接口">
            {realStatus?.read_endpoint_enabled ? "后端内置" : "不可用"}
          </Descriptions.Item>
          <Descriptions.Item label="写入接口">
            {realStatus?.write_endpoint_enabled ? "后端内置" : "不可用"}
          </Descriptions.Item>
          <Descriptions.Item label="导入条件">
            {realStatus?.ready_for_import ? "已满足" : `缺少 ${missingTencentDocsItems.join("、") || "配置"}`}
          </Descriptions.Item>
          <Descriptions.Item label="导出条件">
            {realStatus?.ready_for_export ? "已满足" : `缺少 ${missingTencentDocsItems.join("、") || "配置"}`}
          </Descriptions.Item>
          <Descriptions.Item label="最后探测错误">
            {realStatus?.last_probe_error || "-"}
          </Descriptions.Item>
        </Descriptions>
        {(realStatus?.sheet_id_candidates || []).length ? (
          <Table<SheetCandidate>
            rowKey={(record, index) => record.sheetId || String(index)}
            size="small"
            style={{ marginTop: 12 }}
            pagination={false}
            dataSource={realStatus?.sheet_id_candidates || []}
            columns={[
              { title: "sheetID 候选", dataIndex: "sheetId", width: 180 },
              { title: "标题", dataIndex: "title", width: 160 },
              { title: "行数", dataIndex: "rowCount", width: 90 },
              { title: "列数", dataIndex: "columnCount", width: 90 },
            ]}
          />
        ) : null}
      </Card>

      {realStatus?.token_expiry_status === "expired" ? (
        <Alert
          type="error"
          showIcon
          message="腾讯文档 token 已超过设置的过期时间，请更新 access_token 和有效期。"
        />
      ) : null}

      {realStatus?.token_expiry_status === "expiring_soon" ? (
        <Alert
          type="warning"
          showIcon
          message={`腾讯文档 token 即将过期，剩余有效期：${realStatus.token_remaining_text || "-"}`}
        />
      ) : null}

      {realStatus?.ready_for_direct_token && (!realStatus?.ready_for_import || !realStatus?.ready_for_export) ? (
        <Alert
          type="warning"
          showIcon
          message="Direct Token 已配置，但腾讯文档导入/导出条件尚未完全满足。"
          description={`缺少：${missingTencentDocsItems.join("、") || "未知配置"}。请优先确认 encoded_id/fileID、bookID、sheetID 和 range；读取/写入 API 路径已由后端内置。${realStatus?.last_probe_error ? ` 最近探测错误：${realStatus.last_probe_error}` : ""}`}
        />
      ) : null}

      {sheetsDebug ? (
        <Card size="small" title="腾讯文档 Sheet 调试信息">
          {sheetsDebug.sheet_id_warning ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="sheetID 配置警告"
              description={sheetsDebug.sheet_id_warning}
            />
          ) : null}
          <Descriptions size="small" column={3}>
            <Descriptions.Item label="配置的 sheetID">
              {sheetsDebug.configured_sheet_id || "未配置"}
            </Descriptions.Item>
            <Descriptions.Item label="file_id">{sheetsDebug.file_id || "-"}</Descriptions.Item>
            <Descriptions.Item label="HTTP 状态">
              {sheetsDebug.raw_response?.http_status ?? "-"}
            </Descriptions.Item>
            <Descriptions.Item label="ret/code">
              {sheetsDebug.raw_response?.ret ?? sheetsDebug.raw_response?.code ?? "-"}
            </Descriptions.Item>
            <Descriptions.Item label="msg/message">
              {sheetsDebug.raw_response?.msg ?? sheetsDebug.raw_response?.message ?? "-"}
            </Descriptions.Item>
          </Descriptions>
          <Table<SheetCandidate>
            rowKey={(record, index) => record.sheetId || String(index)}
            size="small"
            style={{ marginTop: 12 }}
            pagination={false}
            dataSource={sheetsDebug.sheet_id_candidates || []}
            columns={[
              { title: "sheetID", dataIndex: "sheetId", width: 180 },
              { title: "id", dataIndex: "id", width: 140 },
              { title: "标题", dataIndex: "title", width: 140 },
              { title: "名称", dataIndex: "name", width: 120 },
              { title: "行数", dataIndex: "rowCount", width: 80 },
              { title: "列数", dataIndex: "columnCount", width: 80 },
            ]}
          />
          <Typography.Paragraph
            copyable={{ text: JSON.stringify(sheetsDebug.raw_response?.raw_response ?? {}, null, 2) }}
            style={{ marginTop: 12, maxHeight: 260, overflow: "auto" }}
          >
            <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>
              {JSON.stringify(sheetsDebug.raw_response?.raw_response ?? {}, null, 2)}
            </pre>
          </Typography.Paragraph>
        </Card>
      ) : null}

      {lastImportResult ? (
        <Alert
          type={(lastImportResult.failed_count ?? lastImportResult.failed ?? 0) > 0 ? "warning" : "success"}
          showIcon
          message="最近一次导入结果"
          description={
            <Space size={24} wrap>
              <Typography.Text>新增：{getImportCounts(lastImportResult).created}</Typography.Text>
              <Typography.Text>跳过：{getImportCounts(lastImportResult).skipped}</Typography.Text>
              <Typography.Text>失败：{getImportCounts(lastImportResult).failed}</Typography.Text>
              {lastImportResult.log_id ? (
                <Typography.Text type="secondary">日志 ID：{lastImportResult.log_id}</Typography.Text>
              ) : null}
            </Space>
          }
        />
      ) : null}

      {allMonthsResult ? (
        <Card size="small" title={allMonthsResult.mode === "all_months" ? "全年操作结果" : "操作结果"}>
          <Descriptions size="small" column={4}>
            <Descriptions.Item label="年份">{allMonthsResult.year}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Typography.Text
                style={{
                  color: allMonthsResult.status === "success" ? "#16a34a" : allMonthsResult.status === "partial_success" ? "#d97706" : "#dc2626",
                  fontWeight: 600,
                }}
              >
                {allMonthsResult.status === "success" ? "成功" : allMonthsResult.status === "partial_success" ? "部分成功" : "失败"}
              </Typography.Text>
            </Descriptions.Item>
            {allMonthsResult.total_inserted !== undefined ? (
              <>
                <Descriptions.Item label="新增">{allMonthsResult.total_inserted}</Descriptions.Item>
                <Descriptions.Item label="跳过">{allMonthsResult.total_skipped}</Descriptions.Item>
                <Descriptions.Item label="失败">{allMonthsResult.total_failed}</Descriptions.Item>
              </>
            ) : null}
            {allMonthsResult.total_written_patch_count !== undefined ? (
              <>
                <Descriptions.Item label="写入 patch">{allMonthsResult.total_written_patch_count}</Descriptions.Item>
                <Descriptions.Item label="跳过重复">{allMonthsResult.total_skipped_duplicate_count}</Descriptions.Item>
                <Descriptions.Item label="失败 patch">{allMonthsResult.total_failed_patch_count}</Descriptions.Item>
              </>
            ) : null}
          </Descriptions>
          <Table<any>
            rowKey="month"
            size="small"
            style={{ marginTop: 12 }}
            pagination={false}
            dataSource={allMonthsResult.per_month_results || []}
            columns={[
              { title: "月份", dataIndex: "month", width: 60 },
              { title: "sheetID", dataIndex: "sheet_id", width: 100 },
              { title: "标题", dataIndex: "sheet_title", width: 100 },
              {
                title: "状态",
                dataIndex: "status",
                width: 100,
                render: (v: string) => (
                  <Typography.Text
                    style={{
                      color: v === "success" ? "#16a34a" : v === "sheet_not_found" ? "#d97706" : "#dc2626",
                      fontWeight: 600,
                    }}
                  >
                    {v === "success" ? "成功" : v === "partial_success" ? "部分成功" : v === "sheet_not_found" ? "未找到" : "失败"}
                  </Typography.Text>
                ),
              },
              { title: "新增/写入", dataIndex: "inserted_count", width: 70, render: (_: any, r: any) => r.inserted_count ?? r.written_patch_count ?? "-" },
              { title: "跳过", dataIndex: "skipped_count", width: 60, render: (_: any, r: any) => r.skipped_count ?? r.skipped_duplicate_count ?? "-" },
              { title: "失败", dataIndex: "failed_count", width: 60, render: (_: any, r: any) => r.failed_count ?? r.failed_patch_count ?? "-" },
              { title: "消息", dataIndex: "message", ellipsis: true },
            ]}
          />
        </Card>
      ) : null}

      {writeCellResult ? (
        <Card size="small" title="Write-Cell 测试结果">
          <Descriptions size="small" column={3}>
            <Descriptions.Item label="bookID 使用">
              {writeCellResult.book_id_used || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="fileID 使用">
              {writeCellResult.file_id_used || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="sheetID 使用">
              {writeCellResult.sheet_id_used || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="测试范围">
              {writeCellResult.range_used || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="测试值">
              {writeCellResult.test_value || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="任一成功">
              {writeCellResult.any_success ? "是" : "否"}
            </Descriptions.Item>
          </Descriptions>
          <Alert
            type={writeCellResult.any_success ? "success" : "warning"}
            showIcon
            style={{ marginTop: 8 }}
            message={
              writeCellResult.any_success
                ? "请打开腾讯文档第一个 sheet，查看左上角 A1 单元格是否出现测试值。"
                : "本次仅测试 000001!A1:A1，没有写入其他 sheet。"
            }
          />
          {(writeCellResult.attempts || []).map((attempt: any, idx: number) => (
            <Alert
              key={idx}
              type={attempt.success ? "success" : "error"}
              showIcon
              style={{ marginTop: 8 }}
              message={attempt.label || `Attempt ${idx + 1}`}
              description={
                <Space direction="vertical" size={4}>
                  <Typography.Text>URL: {attempt.request_url || "-"}</Typography.Text>
                  <Typography.Text>
                    HTTP {attempt.http_status ?? "-"}, code={attempt.code ?? "-"}, msg={attempt.msg ?? "-"}
                  </Typography.Text>
                  {!attempt.success ? (
                    <Typography.Paragraph
                      copyable={{ text: JSON.stringify(attempt.raw_response ?? {}, null, 2) }}
                      style={{ maxHeight: 160, overflow: "auto" }}
                    >
                      <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 12 }}>
                        {JSON.stringify(attempt.raw_response ?? {}, null, 2)}
                      </pre>
                    </Typography.Paragraph>
                  ) : null}
                </Space>
              }
            />
          ))}
        </Card>
      ) : null}

      <Card size="small" title="同步日志">
        {importDryRunResult ? (
          <>
            <Alert
              type={importDryRunResult.api_error ? "error" : "info"}
              showIcon
              style={{ marginBottom: 12 }}
              message={
                importDryRunResult.api_error
                  ? `导入预检失败：API 错误 code=${importDryRunResult.api_error.code}`
                  : `导入预检：解析 ${importDryRunResult.parsed_records_count || 0} 条，试剂 ${importDryRunResult.reagent_count || 0} 种`
              }
              description={
                importDryRunResult.api_error ? (
                  <Space direction="vertical" size={4}>
                    <Typography.Text>
                      URL: {importDryRunResult.request_url || "-"}
                    </Typography.Text>
                    <Typography.Text>
                      HTTP {importDryRunResult.http_status ?? "-"}, code={importDryRunResult.api_error.code}, msg={importDryRunResult.api_error.msg || "-"}
                    </Typography.Text>
                  </Space>
                ) : (
                  <Space direction="vertical" size={4}>
                    <Typography.Text>
                      range: {importDryRunResult.range || "-"}, sheet: {importDryRunResult.sheet_id || "-"}
                    </Typography.Text>
                    <Typography.Text>
                      parsed_values_shape: {JSON.stringify(importDryRunResult.parsed_values_shape || [])}
                    </Typography.Text>
                    <Typography.Text>试剂列: {JSON.stringify(importDryRunResult.detected_reagent_columns?.map((c: any) => c.reagent_name) || [])}</Typography.Text>
                    <Typography.Text>前 10 条: {JSON.stringify(importDryRunResult.parsed_records_preview || [])}</Typography.Text>
                    {importDryRunResult.reagent_count === 0 && importDryRunResult.parsed_values_shape && importDryRunResult.parsed_values_shape[0] > 0 ? (
                      <Alert
                        type="warning"
                        showIcon
                        style={{ marginTop: 8 }}
                        message="parsed_values 非空但 reagent_count=0，第 2 行内容可能行列索引错位"
                        description={`Row 1: ${JSON.stringify(importDryRunResult.matrix_row_1_preview || [])}` + "\n" + `Row 2: ${JSON.stringify(importDryRunResult.matrix_row_2_preview || [])}`}
                      />
                    ) : null}
                  </Space>
                )
              }
            />
            {importDryRunResult.raw_response ? (
              <Typography.Paragraph
                copyable={{ text: JSON.stringify(importDryRunResult.raw_response, null, 2) }}
                style={{ maxHeight: 200, overflow: "auto" }}
              >
                <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 12 }}>
                  {JSON.stringify(importDryRunResult.raw_response, null, 2)}
                </pre>
              </Typography.Paragraph>
            ) : null}
          </>
        ) : null}
        {exportPreviewResult ? (
          <Alert
            type={exportPreviewResult.status === "read_failed" ? "error" : "info"}
            showIcon
            style={{ marginBottom: 12 }}
            message={`追加预览：数据库记录 ${exportPreviewResult.db_records_count || 0} 条，写入范围 ${exportPreviewResult.write_range || "B4:BF34"}，矩阵 ${exportPreviewResult.actual_shape || exportPreviewResult.expected_shape || "31x57"}`}
            description={
              exportPreviewResult.status === "read_failed"
                ? `读取现有 B4:BF34 失败：${JSON.stringify(exportPreviewResult.read_error || {})}`
                : `原有非空单元格 ${exportPreviewResult.existing_cells_count || 0}，数据库三元组 ${exportPreviewResult.new_tuples_count || 0}，真正追加 ${exportPreviewResult.appended_tuples_count || 0}，跳过重复 ${exportPreviewResult.skipped_duplicate_tuples_count ?? exportPreviewResult.deduped_tuples_count ?? 0}，变更单元格 ${exportPreviewResult.changed_cells_count || 0}。变更预览：${JSON.stringify((exportPreviewResult.preview_changes || []).slice(0, 10))}`
            }
          />
        ) : null}
        <Table<SyncLog>
          rowKey="id"
          size="small"
          dataSource={logs}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "ID", dataIndex: "id", width: 72 },
            { title: "来源", dataIndex: "source" },
            { title: "类型", dataIndex: "sync_type" },
            { title: "状态", dataIndex: "status" },
            { title: "消息", dataIndex: "message" },
            {
              title: "时间",
              dataIndex: "created_at",
              render: (value: string) => formatBeijingTime(value),
            },
          ]}
        />
      </Card>

      <Modal
        title="从腾讯文档导入"
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        footer={
          <Space>
            <Button onClick={() => setImportModalOpen(false)}>取消</Button>
            <Button type="primary" loading={realSyncLoading} onClick={confirmImport}>
              确认导入
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          <Alert
            type="info"
            showIcon
            message="请选择导入范围，后端会根据所选年月自动解析对应 sheetID。"
          />
          <Space>
            <Button
              type={importModalMode === "single" ? "primary" : "default"}
              onClick={() => setImportModalMode("single")}
            >
              单月导入
            </Button>
            <Button
              type={importModalMode === "all" ? "primary" : "default"}
              onClick={() => setImportModalMode("all")}
            >
              全年导入
            </Button>
          </Space>
          <Space>
            <InputNumber
              min={2000}
              max={2100}
              value={importModalYear}
              onChange={(v) => v && setImportModalYear(v)}
              addonBefore="年份"
              style={{ width: 130 }}
            />
            {importModalMode === "single" ? (
              <InputNumber
                min={1}
                max={12}
                value={importModalMonth}
                onChange={(v) => v && setImportModalMonth(v)}
                addonBefore="月份"
                style={{ width: 130 }}
              />
            ) : null}
          </Space>
          <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
            {importModalMode === "single"
              ? "单月导入：将从腾讯文档对应月份 sheet 导入出入库流水到数据库。"
              : "全年导入：将依次导入该年份 1-12 月所有 sheet。"}
          </Typography.Paragraph>
        </Space>
      </Modal>

      <Modal
        title="同步到腾讯文档"
        open={exportModalOpen}
        onCancel={() => setExportModalOpen(false)}
        footer={
          <Space>
            <Button onClick={() => setExportModalOpen(false)}>取消</Button>
            <Button type="primary" loading={realSyncLoading} onClick={confirmExport}>
              确认同步
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          <Alert
            type="info"
            showIcon
            message="同步采用非破坏性增量追加方式：系统会读取腾讯文档已有单元格，在原有内容后追加数据库中的出入库记录，不会清空原表。"
          />
          <Space>
            <Button
              type={exportModalMode === "single" ? "primary" : "default"}
              onClick={() => setExportModalMode("single")}
            >
              单月同步
            </Button>
            <Button
              type={exportModalMode === "all" ? "primary" : "default"}
              onClick={() => setExportModalMode("all")}
            >
              全年同步
            </Button>
          </Space>
          <Space>
            <InputNumber
              min={2000}
              max={2100}
              value={exportModalYear}
              onChange={(v) => v && setExportModalYear(v)}
              addonBefore="年份"
              style={{ width: 130 }}
            />
            {exportModalMode === "single" ? (
              <InputNumber
                min={1}
                max={12}
                value={exportModalMonth}
                onChange={(v) => v && setExportModalMonth(v)}
                addonBefore="月份"
                style={{ width: 130 }}
              />
            ) : null}
          </Space>
          <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
            {exportModalMode === "single"
              ? "单月同步：将数据库出入库流水追加写入对应月份 sheet。"
              : "全年同步：将依次处理该年份 1-12 月所有 sheet。"}
          </Typography.Paragraph>
        </Space>
      </Modal>

      <Modal
        title="更新腾讯文档 Token 有效期"
        open={tokenExpiryModalOpen}
        onCancel={() => setTokenExpiryModalOpen(false)}
        footer={
          <Space>
            <Button onClick={() => setTokenExpiryModalOpen(false)}>取消</Button>
            <Button danger loading={tokenExpirySaving} onClick={() => saveTokenExpiry(true)}>
              清除有效期
            </Button>
            <Button type="primary" loading={tokenExpirySaving} onClick={() => saveTokenExpiry(false)}>
              保存
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          <Alert
            type="info"
            showIcon
            message="Direct Token 模式下系统无法自动读取 token 的真实过期时间。这里保存的是人工维护的过期提醒时间，不会自动刷新 access_token。"
          />
          <Typography.Text type="secondary">
            当前保存值：{formatBeijingTime(realStatus?.token_expires_at)}
          </Typography.Text>
          <input
            type="datetime-local"
            step={1}
            value={tokenExpiryInput}
            onChange={(event) => setTokenExpiryInput(event.target.value)}
            style={{
              width: "100%",
              height: 36,
              padding: "4px 11px",
              border: "1px solid #d9d9d9",
              borderRadius: 6,
            }}
          />
        </Space>
      </Modal>

      <Modal
        title="导入错误明细"
        open={errorModalOpen}
        onCancel={() => setErrorModalOpen(false)}
        footer={<Button onClick={() => setErrorModalOpen(false)}>关闭</Button>}
        width={760}
      >
        <Table<ImportErrorItem>
          rowKey={(_, index) => String(index)}
          size="small"
          dataSource={errors.slice(0, 100)}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "Sheet", dataIndex: "sheet", width: 110 },
            { title: "行号", dataIndex: "row", width: 80 },
            { title: "试剂", dataIndex: "reagent", width: 160 },
            { title: "原因", dataIndex: "reason" },
          ]}
        />
        {errors.length > 100 ? (
          <Typography.Text type="secondary">仅展示前 100 条错误，请查看同步日志获取摘要。</Typography.Text>
        ) : null}
      </Modal>
    </Space>
  );
}
