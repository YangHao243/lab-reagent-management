import { Button, Card, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type AlertEvent = {
  id: number;
  year_display_id?: number;
  reagent_id: number;
  alert_type: string;
  level: string;
  message: string;
  is_resolved: boolean;
  resolved_at?: string;
  created_at: string;
};

export default function Alerts() {
  const { hasRole } = useAuth();
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [year, setYear] = useState<number>(() => new Date().getFullYear());
  const canHandleAlerts = hasRole("manager", "admin", "superadmin");

  const loadEvents = (nextYear = year) => {
    setLoading(true);
    apiClient
      .get<AlertEvent[]>("/alerts/events", { params: { year: nextYear } })
      .then((response) => setEvents(response.data))
      .catch(() => message.warning("报警事件加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadEvents();
  }, []);

  const checkAlerts = () => {
    apiClient
      .post("/alerts/check")
      .then(() => {
        message.success("报警检查完成");
        loadEvents();
      })
      .catch(() => message.error("报警检查失败"));
  };

  const resolveAlert = (id: number) => {
    apiClient
      .put(`/alerts/events/${id}/resolve`)
      .then(() => {
        message.success("报警已处理");
        loadEvents();
      })
      .catch(() => message.error("处理失败"));
  };

  const handleAll = () => {
    Modal.confirm({
      title: "确认一键处理？",
      content:
        "将批量处理当前所有未处理报警事件，处理后状态将变为已处理。是否继续？",
      okText: "确认处理",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: () => {
        apiClient
          .post("/alerts/handle-all")
          .then((response) => {
            const data = response.data as { handled_count: number; message: string };
            message.success(data.message || "批量处理完成");
            loadEvents();
          })
          .catch(() => message.error("批量处理失败"));
      },
    });
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          报警事件
        </Typography.Title>
        <Space>
          <Select
            value={year}
            onChange={(value) => {
              setYear(value);
              loadEvents(value);
            }}
            style={{ width: 120 }}
            options={Array.from(
              { length: new Date().getFullYear() - 2021 },
              (_, index) => {
                const y = 2022 + index;
                return { label: `${y} 年`, value: y };
              },
            )}
          />
          {canHandleAlerts && (
            <>
              <Button type="primary" danger onClick={handleAll}>
                一键处理
              </Button>
              <Button type="primary" onClick={checkAlerts}>
                执行检查
              </Button>
            </>
          )}
        </Space>
      </Space>
      <Card size="small">
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={events}
          pagination={{ pageSize: 12 }}
          columns={[
            { title: "ID", dataIndex: "year_display_id", width: 72 },
            { title: "试剂ID", dataIndex: "reagent_id", width: 88 },
            { title: "类型", dataIndex: "alert_type", width: 120 },
            { title: "级别", dataIndex: "level", width: 100 },
            { title: "消息", dataIndex: "message" },
            {
              title: "状态",
              dataIndex: "is_resolved",
              width: 100,
              render: (value: boolean) => (value ? <Tag color="green">已处理</Tag> : <Tag color="red">未处理</Tag>),
            },
            {
              title: "创建时间",
              dataIndex: "created_at",
              render: (value: string) => new Date(value).toLocaleString(),
            },
            {
              title: "操作",
              width: 96,
              render: (_, record) => (
                <Button size="small" disabled={record.is_resolved || !canHandleAlerts} onClick={() => resolveAlert(record.id)}>
                  处理
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
