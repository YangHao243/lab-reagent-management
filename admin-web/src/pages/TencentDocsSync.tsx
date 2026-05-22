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
  client_id_configured: boolean;
  client_secret_configured: boolean;
  redirect_uri_configured: boolean;
  doc_id_configured: boolean;
  doc_id?: string | null;
  default_year: number;
  token_saved: boolean;
  token_valid: boolean;
  token_expires_at?: string | null;
  open_id_saved: boolean;
  ready_for_oauth: boolean;
  ready_for_sync: boolean;
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
  errors: ImportErrorItem[];
  log_id: number;
  created_reagents?: number;
  updated_reagents?: number;
};

function shouldShowImportError(error: ImportErrorItem) {
  const reason = error.reason || "";
  return !reason.includes("操作人不能为空") && !reason.includes("库存不足");
}

export default function TencentDocsSync() {
  const { hasRole } = useAuth();
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [realStatus, setRealStatus] = useState<TencentDocsRealStatus | null>(null);
  const [logs, setLogs] = useState<SyncLog[]>([]);
  const [exportYear, setExportYear] = useState<number>(2026);
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [realSyncLoading, setRealSyncLoading] = useState(false);
  const [errors, setErrors] = useState<ImportErrorItem[]>([]);
  const [errorModalOpen, setErrorModalOpen] = useState(false);
  const canOperateSync = hasRole("admin", "superadmin");
  const showMockButtons = canOperateSync && status?.mock_enabled !== false;

  const loadData = () => {
    Promise.all([
      apiClient.get<SyncStatus>("/api/sync/status"),
      apiClient.get<TencentDocsRealStatus>("/api/tencent-docs/status"),
      apiClient.get<SyncLog[]>("/api/sync/logs"),
    ])
      .then(([statusResponse, realStatusResponse, logsResponse]) => {
        setStatus(statusResponse.data);
        setRealStatus(realStatusResponse.data);
        setLogs(logsResponse.data);
      })
      .catch(() => message.warning("同步状态加载失败"));
  };

  useEffect(() => {
    loadData();
  }, []);

  const runMockImport = () => {
    apiClient
      .post("/api/sync/mock/import")
      .then(() => {
        message.success("mock 导入完成");
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
      message.success(result.message || "文件导入完成");
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

  const importFromTencentDocs = async () => {
    setRealSyncLoading(true);
    try {
      await apiClient.post("/api/tencent-docs/import", null, { params: { year: exportYear } });
      message.success("腾讯文档导入完成");
      loadData();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "腾讯文档导入尚未可用");
    } finally {
      setRealSyncLoading(false);
    }
  };

  const exportToTencentDocs = async () => {
    setRealSyncLoading(true);
    try {
      await apiClient.post("/api/tencent-docs/export", null, { params: { year: exportYear } });
      message.success("已同步到腾讯文档");
      loadData();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "同步到腾讯文档尚未可用");
    } finally {
      setRealSyncLoading(false);
    }
  };

  const renderConfigured = (value?: boolean) => (value ? "已配置" : "未配置");
  const renderSaved = (value?: boolean) => (value ? "已保存" : "未保存");
  const tokenStatusText = !realStatus?.token_saved
    ? "未授权"
    : realStatus.token_valid
      ? "有效"
      : "已过期";

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
          <Descriptions.Item label="client_id">{renderConfigured(realStatus?.client_id_configured)}</Descriptions.Item>
          <Descriptions.Item label="client_secret">{renderConfigured(realStatus?.client_secret_configured)}</Descriptions.Item>
          <Descriptions.Item label="redirect_uri">{renderConfigured(realStatus?.redirect_uri_configured)}</Descriptions.Item>
          <Descriptions.Item label="doc_id">{realStatus?.doc_id_configured ? realStatus.doc_id : "未配置"}</Descriptions.Item>
          <Descriptions.Item label="token">{renderSaved(realStatus?.token_saved)}</Descriptions.Item>
          <Descriptions.Item label="token 状态">{tokenStatusText}</Descriptions.Item>
          <Descriptions.Item label="token 过期时间">{formatBeijingTime(realStatus?.token_expires_at)}</Descriptions.Item>
          <Descriptions.Item label="open_id">{realStatus?.open_id_saved ? "已获取" : "未获取"}</Descriptions.Item>
          <Descriptions.Item label="OAuth 条件">{realStatus?.ready_for_oauth ? "已满足" : "缺少配置"}</Descriptions.Item>
          <Descriptions.Item label="同步条件">{realStatus?.ready_for_sync ? "已满足" : "未授权或 token 无效"}</Descriptions.Item>
        </Descriptions>
      </Card>

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
              <Button
                onClick={importFromTencentDocs}
                disabled={!realStatus?.ready_for_sync}
                loading={realSyncLoading}
              >
                从腾讯文档导入
              </Button>
              <Button
                onClick={exportToTencentDocs}
                disabled={!realStatus?.ready_for_sync}
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
              <Button onClick={downloadExportFile} loading={exporting}>
                导出 Excel
              </Button>
            </>
          ) : (
            <Typography.Text type="secondary">当前角色仅可查看同步状态和日志</Typography.Text>
          )}
        </Space>
      </Card>

      <Card size="small" title="同步日志">
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
