import { Alert, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

type Summary = {
  total_reagents: number;
  low_stock_count: number;
  today_in_count: number;
  today_out_count: number;
  month_in_count: number;
  month_out_count: number;
};

type Reagent = {
  id: number;
  name_cn: string;
  name_en?: string;
  category?: string;
  current_quantity: number;
  warning_threshold: number;
  purity_grade?: string;
  unit?: string;
  location?: string;
};

const defaultSummary: Summary = {
  total_reagents: 0,
  low_stock_count: 0,
  today_in_count: 0,
  today_out_count: 0,
  month_in_count: 0,
  month_out_count: 0,
};

function getApiError(error: unknown, fallback: string) {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail ===
      "string"
  ) {
    return (error as { response: { data: { detail: string } } }).response.data.detail;
  }
  return fallback;
}

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary>(defaultSummary);
  const [lowStock, setLowStock] = useState<Reagent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 仪表盘首屏同时加载系统总览和低库存列表，减少页面等待次数。
  const loadDashboard = () => {
    setLoading(true);
    setError("");

    Promise.all([
      apiClient.get<Summary>("/reports/summary"),
      apiClient.get<Reagent[]>("/alerts/low-stock"),
    ])
      .then(([summaryResponse, lowStockResponse]) => {
        setSummary(summaryResponse.data);
        setLowStock(
          [...lowStockResponse.data].sort((a, b) => a.id - b.id),
        );
      })
      .catch((requestError) => {
        setError(getApiError(requestError, "仪表盘数据加载失败，请确认后端服务已启动"));
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  const stats = [
    { title: "试剂总数", value: summary.total_reagents },
    { title: "低库存试剂数", value: summary.low_stock_count, color: "#cf1322" },
    { title: "今日入库次数", value: summary.today_in_count, color: "#389e0d" },
    { title: "今日出库次数", value: summary.today_out_count, color: "#cf1322" },
    { title: "本月入库次数", value: summary.month_in_count, color: "#389e0d" },
    { title: "本月出库次数", value: summary.month_out_count, color: "#cf1322" },
  ];

  const columns: ColumnsType<Reagent> = [
    { title: "ID", dataIndex: "id", width: 70 },
    { title: "试剂中文名", dataIndex: "name_cn", width: 200, ellipsis: true },
    {
      title: "英文名",
      dataIndex: "name_en",
      width: 260,
      ellipsis: true,
      render: (value: string | undefined) => value || "-",
    },
    { title: "分类", dataIndex: "category", width: 110 },
    {
      title: "当前库存",
      width: 120,
      render: (_, record) => (
        <Tag color="red">
          {record.current_quantity} {record.unit || ""}
        </Tag>
      ),
    },
    {
      title: "预警阈值",
      width: 120,
      render: (_, record) => `${record.warning_threshold} ${record.unit || ""}`,
    },
    {
      title: "纯度等级",
      dataIndex: "purity_grade",
      width: 110,
      render: (value: string | undefined) => value || "-",
    },
    { title: "存放位置", dataIndex: "location", width: 110 },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space direction="vertical" size={4}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          仪表盘
        </Typography.Title>
        <Typography.Text type="secondary">查看库存概况、出入库频次和需要优先处理的低库存试剂。</Typography.Text>
      </Space>

      {error && <Alert type="warning" message={error} showIcon />}

      <Row gutter={[16, 16]}>
        {stats.map((item) => (
          <Col key={item.title} xs={24} sm={12} lg={8} xl={4}>
            <Card size="small" loading={loading}>
              <Statistic
                title={item.title}
                value={item.value}
                valueStyle={item.color ? { color: item.color } : undefined}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        size="small"
        title="低库存试剂"
        extra={<Typography.Text type="secondary">共 {lowStock.length} 项</Typography.Text>}
      >
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={lowStock}
          columns={columns}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 1100 }}
        />
      </Card>
    </Space>
  );
}
