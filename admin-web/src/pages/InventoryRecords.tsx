import {
  Button,
  Card,
  Form,
  Empty,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState, type Key } from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type OperationType = "in" | "out" | "adjust";

type InventoryRecord = {
  id: number;
  year_display_id?: number;
  reagent_id: number;
  operation_type: OperationType;
  quantity_change: number;
  before_quantity: number;
  after_quantity: number;
  operator_id?: number;
  operator_name?: string;
  reason?: string;
  remark?: string;
  created_at: string;
};

type ReagentOption = {
  id: number;
  label: string;
  value: number;
  name_cn: string;
  standard_name?: string;
  category?: string;
  current_quantity: number;
  unit: string;
  warning_threshold: number;
  location?: string;
  hazard_level?: string;
};

type InventoryOperationValues = {
  reagent_id: number;
  quantity: number;
  operator_name?: string;
  reason?: string;
  remark?: string;
};

type CalendarRecord = {
  id: number;
  reagent_id: number;
  reagent_name: string;
  operation_type: OperationType;
  quantity_change: number;
  operator_name?: string;
  reason?: string;
  remark?: string;
  created_at: string;
};

type CalendarDay = {
  date: string;
  in_count: number;
  out_count: number;
  adjust_count: number;
  in_quantity_total: number;
  out_quantity_total: number;
  records: CalendarRecord[];
};

type InventoryCalendarResponse = {
  year: number;
  month: number;
  days: CalendarDay[];
};

type BatchDeleteResponse = {
  deleted_count: number;
  affected_reagent_ids: number[];
};

const operationMeta: Record<OperationType, { color: string; label: string }> = {
  in: { color: "green", label: "入库" },
  out: { color: "red", label: "出库" },
  adjust: { color: "blue", label: "校正" },
};

const monthOptions = Array.from({ length: 12 }, (_, index) => ({
  label: `${index + 1}月`,
  value: index + 1,
}));

const weekDays = ["日", "一", "二", "三", "四", "五", "六"];

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

function getCurrentYearMonth() {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

function getCalendarCells(year: number, month: number) {
  const firstDay = new Date(year, month - 1, 1).getDay();
  const dayCount = new Date(year, month, 0).getDate();
  return [
    ...Array.from({ length: firstDay }, () => ""),
    ...Array.from({ length: dayCount }, (_, index) => {
      const day = index + 1;
      return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }),
  ];
}

function getQuantityColor(value: number) {
  if (value > 0) return "#389e0d";
  if (value < 0) return "#cf1322";
  return undefined;
}

export default function InventoryRecords() {
  const [form] = Form.useForm<InventoryOperationValues>();
  const watchedReason = Form.useWatch("reason", form);
  const currentYearMonth = getCurrentYearMonth();
  const [year, setYear] = useState<number>(() => new Date().getFullYear());
  const [records, setRecords] = useState<InventoryRecord[]>([]);
  const [reagents, setReagents] = useState<ReagentOption[]>([]);
  const [operationType, setOperationType] = useState<OperationType | undefined>();
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalMode, setModalMode] = useState<"in" | "out">("in");
  const [activeView, setActiveView] = useState("table");
  const [calendarYear, setCalendarYear] = useState(currentYearMonth.year);
  const [calendarMonth, setCalendarMonth] = useState(currentYearMonth.month);
  const [calendarReagentId, setCalendarReagentId] = useState<number | undefined>();
  const [calendarData, setCalendarData] = useState<InventoryCalendarResponse | null>(null);
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [selectedDay, setSelectedDay] = useState<CalendarDay | null>(null);
  const { hasRole } = useAuth();
  const canEditRecord = hasRole("superadmin");
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<InventoryRecord | null>(null);
  const [editForm] = Form.useForm();
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [selectedRecordIds, setSelectedRecordIds] = useState<number[]>([]);
  const [batchDeleting, setBatchDeleting] = useState(false);

  // 加载出入库记录，筛选条件直接传给后端，避免前端重复过滤。
  const loadRecords = (nextType?: OperationType, nextYear = year) => {
    setSelectedRecordIds([]);
    setLoading(true);
    apiClient
      .get<InventoryRecord[]>("/inventory/records", {
        params: { operation_type: nextType, year: nextYear },
      })
      .then((response) => setRecords(response.data))
      .catch((error) => message.error(getApiError(error, "库存记录加载失败")))
      .finally(() => setLoading(false));
  };

  // 入库/出库弹窗使用专用选项接口，避免前端手动输入 reagent_id。
  const loadReagents = () => {
    apiClient
      .get<ReagentOption[]>("/reagents/options", { params: { limit: 500 } })
      .then((response) => setReagents(response.data))
      .catch((error) => message.error(getApiError(error, "试剂列表加载失败")));
  };

  // 加载日历式库存流水，返回整月所有日期，前端可直接渲染日历网格。
  const loadCalendar = (
    year = calendarYear,
    month = calendarMonth,
    reagentId = calendarReagentId,
  ) => {
    setCalendarLoading(true);
    apiClient
      .get<InventoryCalendarResponse>("/reports/inventory-calendar", {
        params: { year, month, reagent_id: reagentId },
      })
      .then((response) => setCalendarData(response.data))
      .catch((error) => message.error(getApiError(error, "日历流水加载失败")))
      .finally(() => setCalendarLoading(false));
  };

  // 操作成功后轻量刷新统计和报警接口，保证 Dashboard/报警页再次进入时看到最新数据。
  const refreshRelatedData = async () => {
    await Promise.allSettled([
      apiClient.get("/reports/summary"),
      apiClient.get("/alerts/low-stock"),
    ]);
  };

  useEffect(() => {
    loadRecords();
    loadReagents();
  }, []);

  const openOperationModal = (mode: "in" | "out") => {
    setModalMode(mode);
    form.resetFields();
    setModalOpen(true);
  };

  // 提交入库或出库操作，成功后刷新记录和试剂库存。
  const submitOperation = async () => {
    const values = await form.validateFields();
    const endpoint = modalMode === "in" ? "/inventory/in" : "/inventory/out";

    setSubmitting(true);
    try {
      await apiClient.post(endpoint, values);
      message.success(modalMode === "in" ? "入库成功" : "出库成功");
      setModalOpen(false);
      form.resetFields();
      loadRecords(operationType);
      loadReagents();
      refreshRelatedData();
      loadCalendar();
    } catch (error) {
      message.error(getApiError(error, modalMode === "in" ? "入库失败" : "出库失败"));
    } finally {
      setSubmitting(false);
    }
  };

  // 打开编辑弹窗，预填当前记录数据。
  const openEditModal = (record: InventoryRecord) => {
    setEditingRecord(record);
    editForm.setFieldsValue({
      quantity: Math.abs(record.quantity_change),
      operator_name: record.operator_name || "",
      reason: record.reason || undefined,
      remark: record.remark || "",
    });
    setEditModalOpen(true);
  };

  // 提交编辑。
  const submitEdit = async () => {
    const values = await editForm.validateFields();
    if (!editingRecord) return;
    setEditSubmitting(true);
    try {
      await apiClient.put(`/inventory/records/${editingRecord.id}`, values);
      message.success("库存流水已更新");
      setEditModalOpen(false);
      setEditingRecord(null);
      editForm.resetFields();
      loadRecords(operationType);
      refreshRelatedData();
      loadCalendar();
    } catch (error) {
      message.error(getApiError(error, "编辑库存流水失败"));
    } finally {
      setEditSubmitting(false);
    }
  };

  // 删除库存流水。
  const deleteRecord = async (record: InventoryRecord) => {
    try {
      await apiClient.delete(`/inventory/records/${record.id}`);
      message.success("库存流水已删除");
      loadRecords(operationType);
      loadReagents();
      refreshRelatedData();
      loadCalendar();
    } catch (error) {
      message.error(getApiError(error, "删除库存流水失败"));
    }
  };

  // 批量删除库存流水，后端会按受影响试剂统一重算库存。
  const batchDeleteRecords = async () => {
    if (selectedRecordIds.length === 0) {
      message.warning("请先选择要删除的库存流水记录");
      return;
    }

    setBatchDeleting(true);
    try {
      const response = await apiClient.post<BatchDeleteResponse>(
        "/inventory/records/batch-delete",
        { record_ids: selectedRecordIds },
      );
      message.success(`已删除 ${response.data.deleted_count} 条库存流水记录`);
      setSelectedRecordIds([]);
      loadRecords(operationType);
      loadReagents();
      refreshRelatedData();
      loadCalendar();
    } catch (error) {
      message.error(getApiError(error, "批量删除库存流水失败"));
    } finally {
      setBatchDeleting(false);
    }
  };

  const columns: ColumnsType<InventoryRecord> = [
    { title: "记录ID", dataIndex: "year_display_id", width: 90 },
    { title: "试剂ID", dataIndex: "reagent_id", width: 90 },
    {
      title: "操作类型",
      dataIndex: "operation_type",
      width: 110,
      render: (value: OperationType) => (
        <Tag color={operationMeta[value]?.color || "default"}>
          {operationMeta[value]?.label || value}
        </Tag>
      ),
    },
    {
      title: "变化数量",
      dataIndex: "quantity_change",
      width: 110,
      render: (value: number, record) => (
        <span style={{ color: getQuantityColor(value) }}>
          {value}
        </span>
      ),
    },
    { title: "操作前数量", dataIndex: "before_quantity", width: 120 },
    { title: "操作后数量", dataIndex: "after_quantity", width: 120 },
    {
      title: "操作员",
      dataIndex: "operator_name",
      width: 100,
      render: (value: string | undefined) => value || "-",
    },
    { title: "原因", dataIndex: "reason", ellipsis: true },
    { title: "备注", dataIndex: "remark", ellipsis: true },
    {
      title: "时间",
      dataIndex: "created_at",
      width: 180,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    ...(canEditRecord
      ? [
          {
            title: "操作",
            width: 160,
            fixed: "right" as const,
            render: (_: unknown, record: InventoryRecord) => (
              <Space size={8}>
                <Button size="small" onClick={() => openEditModal(record)}>
                  编辑
                </Button>
                <Popconfirm
                  title="确认删除该库存流水记录？"
                  description="删除后将重新计算该试剂库存及相关流水的操作前/后数量，此操作仅超级管理员可执行。是否继续？"
                  okText="确认删除"
                  cancelText="取消"
                  onConfirm={() => deleteRecord(record)}
                >
                  <Button size="small" danger>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]
      : []),
  ];

  const calendarRecordColumns: ColumnsType<CalendarRecord> = [
    { title: "试剂名称", dataIndex: "reagent_name" },
    {
      title: "操作类型",
      dataIndex: "operation_type",
      width: 100,
      render: (value: OperationType) => (
        <Tag color={operationMeta[value]?.color || "default"}>
          {operationMeta[value]?.label || value}
        </Tag>
      ),
    },
    {
      title: "数量",
      dataIndex: "quantity_change",
      width: 100,
      render: (value: number, record) => (
        <span style={{ color: getQuantityColor(value) }}>
          {value}
        </span>
      ),
    },
    { title: "操作人", dataIndex: "operator_name", width: 100 },
    { title: "原因", dataIndex: "reason", ellipsis: true },
    { title: "备注", dataIndex: "remark", ellipsis: true },
    {
      title: "时间",
      dataIndex: "created_at",
      width: 180,
      render: (value: string) => new Date(value).toLocaleString(),
    },
  ];

  const dayMap = new Map((calendarData?.days || []).map((day) => [day.date, day]));
  const calendarCells = getCalendarCells(calendarYear, calendarMonth);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space align="center" style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          出入库记录
        </Typography.Title>
        <Space>
          <Button type="primary" onClick={() => openOperationModal("in")}>
            入库
          </Button>
          <Button danger onClick={() => openOperationModal("out")}>
            出库
          </Button>
        </Space>
      </Space>

      <Tabs
        activeKey={activeView}
        onChange={(key) => {
          setActiveView(key);
          if (key === "calendar") {
            setCalendarYear(year);
            loadCalendar(year, calendarMonth, calendarReagentId);
          }
        }}
        items={[
          {
            key: "table",
            label: "表格视图",
            children: (
              <Card size="small">
                <Space wrap style={{ marginBottom: 12 }}>
                  <Select
                    value={year}
                    onChange={(value) => {
                      setYear(value);
                      loadRecords(operationType, value);
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
                  <Select
                    allowClear
                    placeholder="操作类型"
                    value={operationType}
                    onChange={(value) => {
                      const nextType = value as OperationType | undefined;
                      setOperationType(nextType);
                      loadRecords(nextType);
                    }}
                    style={{ width: 180 }}
                    options={[
                      { label: "入库", value: "in" },
                      { label: "出库", value: "out" },
                      { label: "校正", value: "adjust" },
                    ]}
                  />
                  {canEditRecord && (
                    <Popconfirm
                      title={`确认删除选中的 ${selectedRecordIds.length} 条库存流水记录？`}
                      description="删除后将重新计算相关试剂库存及流水前后数量。此操作仅超级管理员可执行。是否继续？"
                      okText="确认删除"
                      cancelText="取消"
                      disabled={selectedRecordIds.length === 0 || batchDeleting}
                      onConfirm={batchDeleteRecords}
                    >
                      <Button
                        danger
                        disabled={selectedRecordIds.length === 0}
                        loading={batchDeleting}
                      >
                        {selectedRecordIds.length > 0
                          ? `批量删除（${selectedRecordIds.length}）`
                          : "批量删除"}
                      </Button>
                    </Popconfirm>
                  )}
                </Space>
                <Table
                  rowKey="id"
                  size="small"
                  loading={loading}
                  dataSource={records}
                  rowSelection={
                    canEditRecord
                      ? {
                          selectedRowKeys: selectedRecordIds,
                          onChange: (selectedRowKeys: Key[]) => {
                            setSelectedRecordIds(selectedRowKeys.map((key) => Number(key)));
                          },
                        }
                      : undefined
                  }
                  pagination={{ pageSize: 12, onChange: () => setSelectedRecordIds([]) }}
                  columns={columns}
                  scroll={{ x: 1240 }}
                />
              </Card>
            ),
          },
          {
            key: "calendar",
            label: "日历视图",
            children: (
              <Card size="small" loading={calendarLoading}>
                <Space wrap style={{ marginBottom: 16 }}>
                  <InputNumber
                    min={2000}
                    max={2100}
                    value={calendarYear}
                    addonAfter="年"
                    onChange={(value) => {
                      const nextYear = Number(value || currentYearMonth.year);
                      setCalendarYear(nextYear);
                      loadCalendar(nextYear, calendarMonth, calendarReagentId);
                    }}
                  />
                  <Select
                    value={calendarMonth}
                    options={monthOptions}
                    style={{ width: 120 }}
                    onChange={(value) => {
                      setCalendarMonth(value);
                      loadCalendar(calendarYear, value, calendarReagentId);
                    }}
                  />
                  <Select
                    allowClear
                    showSearch
                    placeholder="按试剂筛选"
                    optionFilterProp="label"
                    value={calendarReagentId}
                    style={{ minWidth: 320 }}
                    onChange={(value) => {
                      const nextReagentId = value as number | undefined;
                      setCalendarReagentId(nextReagentId);
                      loadCalendar(calendarYear, calendarMonth, nextReagentId);
                    }}
                    options={reagents.map((reagent) => ({
                      label: `${reagent.label || reagent.name_cn}｜库存 ${
                        reagent.current_quantity
                      } ${reagent.unit}｜${reagent.location || "未填写位置"}`,
                      value: reagent.value,
                    }))}
                  />
                  <Button onClick={() => loadCalendar()}>刷新</Button>
                </Space>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(7, minmax(0, 1fr))",
                    borderTop: "1px solid #f0f0f0",
                    borderLeft: "1px solid #f0f0f0",
                  }}
                >
                  {weekDays.map((weekDay) => (
                    <div
                      key={weekDay}
                      style={{
                        padding: 8,
                        textAlign: "center",
                        fontWeight: 600,
                        background: "#fafafa",
                        borderRight: "1px solid #f0f0f0",
                        borderBottom: "1px solid #f0f0f0",
                      }}
                    >
                      {weekDay}
                    </div>
                  ))}
                  {calendarCells.map((dateKey, index) => {
                    const day = dateKey ? dayMap.get(dateKey) : undefined;
                    const recordsPreview = day?.records.slice(0, 2) || [];
                    return (
                      <div
                        key={`${dateKey || "empty"}-${index}`}
                        onClick={() => day && setSelectedDay(day)}
                        style={{
                          minHeight: 132,
                          padding: 8,
                          cursor: day ? "pointer" : "default",
                          background: day?.records.length ? "#fbfffb" : "#fff",
                          borderRight: "1px solid #f0f0f0",
                          borderBottom: "1px solid #f0f0f0",
                        }}
                      >
                        {day ? (
                          <Space direction="vertical" size={6} style={{ width: "100%" }}>
                            <Typography.Text strong>{Number(dateKey.slice(8))}</Typography.Text>
                            <Space size={4} wrap>
                              <Tag color="green">入 {day.in_count}</Tag>
                              <Tag color="red">出 {day.out_count}</Tag>
                              {day.adjust_count > 0 && <Tag color="blue">校 {day.adjust_count}</Tag>}
                            </Space>
                            {recordsPreview.map((record) => (
                              <Typography.Text
                                key={record.id}
                                type="secondary"
                                ellipsis
                                style={{ display: "block", maxWidth: "100%", fontSize: 12 }}
                              >
                                {operationMeta[record.operation_type]?.label || record.operation_type}
                                ：{record.reagent_name} {record.quantity_change}
                              </Typography.Text>
                            ))}
                            {day.records.length > 2 && (
                              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                还有 {day.records.length - 2} 条
                              </Typography.Text>
                            )}
                          </Space>
                        ) : null}
                      </div>
                    );
                  })}
                </div>

                {calendarData && calendarData.days.every((day) => day.records.length === 0) && (
                  <Empty description="本月暂无库存流水" style={{ marginTop: 16 }} />
                )}
              </Card>
            ),
          },
        ]}
      />

      <Modal
        title={modalMode === "in" ? "入库" : "出库"}
        open={modalOpen}
        okText="提交"
        cancelText="取消"
        confirmLoading={submitting}
        onOk={submitOperation}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            label="试剂"
            name="reagent_id"
            rules={[{ required: true, message: "请选择试剂" }]}
          >
            <Select
              showSearch
              placeholder="请选择试剂"
              optionFilterProp="label"
              filterOption={(input, option) =>
                String(option?.label ?? "").toLowerCase().includes(input.toLowerCase())
              }
              options={reagents.map((reagent) => ({
                label: `${reagent.label || reagent.name_cn}｜库存 ${reagent.current_quantity} ${
                  reagent.unit
                }｜${reagent.location || "未填写位置"}`,
                value: reagent.value,
              }))}
            />
          </Form.Item>
          <Form.Item
            label="数量（单位：瓶）"
            name="quantity"
            rules={[
              { required: true, message: "请输入数量" },
              {
                type: "integer",
                min: 1,
                message: "数量必须为大于 0 的整数",
              },
            ]}
          >
            <InputNumber min={1} precision={0} step={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            label="操作员（姓名）"
            name="operator_name"
            rules={[
              { required: true, message: "请输入操作员姓名" },
              { max: 20, message: "操作员姓名不超过 20 个字符" },
            ]}
          >
            <Input placeholder="请输入操作员姓名" maxLength={20} />
          </Form.Item>
          <Form.Item
            label="原因"
            name="reason"
            rules={[{ required: true, message: "请选择原因" }]}
          >
            <Select
              placeholder="请选择原因"
              options={[
                { label: "领料入库", value: "领料入库" },
                { label: "实验领用", value: "实验领用" },
                { label: "其他原因", value: "其他原因" },
              ]}
            />
          </Form.Item>
          <Form.Item
            label="备注"
            name="remark"
            dependencies={["reason"]}
            rules={[
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (
                    getFieldValue("reason") === "其他原因" &&
                    (!value || !String(value).trim())
                  ) {
                    return Promise.reject(
                      new Error("选择其他原因时，请在备注中补充说明"),
                    );
                  }
                  return Promise.resolve();
                },
              }),
            ]}
          >
            <Input.TextArea
              rows={3}
              placeholder={
                watchedReason === "其他原因"
                  ? "请补充说明其他原因"
                  : "可填写批号、领用人或其他说明"
              }
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑库存流水"
        open={editModalOpen}
        okText="提交"
        cancelText="取消"
        confirmLoading={editSubmitting}
        onOk={submitEdit}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingRecord(null);
          editForm.resetFields();
        }}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item label="试剂">
            <Input
              disabled
              value={
                reagents.find((r) => r.id === editingRecord?.reagent_id)?.name_cn || ""
              }
            />
          </Form.Item>
          <Form.Item label="操作类型">
            <Input
              disabled
              value={
                editingRecord
                  ? operationMeta[editingRecord.operation_type]?.label || editingRecord.operation_type
                  : ""
              }
            />
          </Form.Item>
          <Form.Item
            label="数量（单位：瓶）"
            name="quantity"
            rules={[
              { required: true, message: "请输入数量" },
              {
                type: "integer",
                min: 1,
                message: "数量必须为大于 0 的整数",
              },
            ]}
          >
            <InputNumber min={1} precision={0} step={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            label="操作员（姓名）"
            name="operator_name"
            rules={[
              { required: true, message: "请输入操作员姓名" },
              { max: 20, message: "操作员姓名不超过 20 个字符" },
            ]}
          >
            <Input placeholder="请输入操作员姓名" maxLength={20} />
          </Form.Item>
          <Form.Item
            label="原因"
            name="reason"
            rules={[{ required: true, message: "请选择原因" }]}
          >
            <Select
              placeholder="请选择原因"
              options={[
                { label: "领料入库", value: "领料入库" },
                { label: "实验领用", value: "实验领用" },
                { label: "其他原因", value: "其他原因" },
              ]}
            />
          </Form.Item>
          <Form.Item
            label="备注"
            name="remark"
            dependencies={["reason"]}
            rules={[
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (
                    getFieldValue("reason") === "其他原因" &&
                    (!value || !String(value).trim())
                  ) {
                    return Promise.reject(
                      new Error("选择其他原因时，请在备注中补充说明"),
                    );
                  }
                  return Promise.resolve();
                },
              }),
            ]}
          >
            <Input.TextArea
              rows={3}
              placeholder={
                Form.useWatch("reason", editForm) === "其他原因"
                  ? "请补充说明其他原因"
                  : "可填写批号、领用人或其他说明"
              }
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={selectedDay ? `${selectedDay.date} 库存流水` : "库存流水"}
        open={Boolean(selectedDay)}
        footer={null}
        width={900}
        onCancel={() => setSelectedDay(null)}
      >
        <Table
          rowKey="id"
          size="small"
          dataSource={selectedDay?.records || []}
          columns={calendarRecordColumns}
          pagination={false}
          locale={{ emptyText: "当天暂无库存流水" }}
          scroll={{ x: 860 }}
        />
      </Modal>
    </Space>
  );
}
