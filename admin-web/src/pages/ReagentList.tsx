import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type Reagent = {
  id: number;
  name_cn: string;
  name_en?: string | null;
  cas_no?: string | null;
  purity_grade?: string | null;
  category?: string | null;
  specification?: string | null;
  unit: string;
  current_quantity: number;
  warning_threshold: number;
  location?: string | null;
  supplier?: string | null;
  hazard_level?: string | null;
  expiry_date?: string | null;
  msds_url?: string | null;
  remark?: string | null;
  adjustment_record_created?: boolean;
  adjustment_record_id?: number | null;
};

type ReagentFormValues = {
  name_cn: string;
  name_en?: string;
  cas_no?: string;
  category?: string;
  specification?: string;
  unit: string;
  current_quantity: number;
  warning_threshold: number;
  location?: string;
  supplier?: string;
  hazard_level?: string;
  expiry_date?: string;
  msds_url?: string;
  remark?: string;
};

function getApiError(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

function normalizeFormValues(values: ReagentFormValues) {
  // 后端可选字段使用 null 表示空值，避免空字符串触发日期等字段校验错误。
  const optionalFields: Array<keyof ReagentFormValues> = [
    "name_en",
    "cas_no",
    "category",
    "specification",
    "location",
    "supplier",
    "hazard_level",
    "expiry_date",
    "msds_url",
    "remark",
  ];
  const payload: Record<string, unknown> = { ...values };
  optionalFields.forEach((field) => {
    if (payload[field] === "") {
      payload[field] = null;
    }
  });
  return payload;
}

export default function ReagentList() {
  const { hasRole } = useAuth();
  const [reagents, setReagents] = useState<Reagent[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState<string | undefined>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingReagent, setEditingReagent] = useState<Reagent | null>(null);
  const [form] = Form.useForm<ReagentFormValues>();
  const canManageReagent = hasRole("manager", "admin", "superadmin");
  const canDeleteReagent = hasRole("admin", "superadmin");

  const loadCategories = () => {
    apiClient
      .get<string[]>("/reagents/categories/list")
      .then((response) => setCategories(response.data))
      .catch((error) => message.error(getApiError(error, "分类列表加载失败")));
  };

  const loadReagents = (nextKeyword = keyword, nextCategory = category) => {
    setLoading(true);
    apiClient
      .get<Reagent[]>("/reagents/", {
        params: {
          keyword: nextKeyword || undefined,
          category: nextCategory || undefined,
        },
      })
      .then((response) => setReagents([...response.data].sort((a, b) => a.id - b.id)))
      .catch((error) => message.error(getApiError(error, "试剂列表加载失败")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadCategories();
    loadReagents("", undefined);
  }, []);

  const openCreateModal = () => {
    setEditingReagent(null);
    form.resetFields();
    form.setFieldsValue({
      unit: "瓶",
      current_quantity: 0,
      warning_threshold: 10,
    });
    setModalOpen(true);
  };

  const openEditModal = (reagent: Reagent) => {
    setEditingReagent(reagent);
    form.setFieldsValue({
      name_cn: reagent.name_cn,
      name_en: reagent.name_en || "",
      cas_no: reagent.cas_no || "",
      category: reagent.category || "",
      specification: reagent.specification || "",
      unit: reagent.unit,
      current_quantity: reagent.current_quantity,
      warning_threshold: reagent.warning_threshold,
      location: reagent.location || "",
      supplier: reagent.supplier || "",
      hazard_level: reagent.hazard_level || "",
      expiry_date: reagent.expiry_date || "",
      msds_url: reagent.msds_url || "",
      remark: reagent.remark || "",
    });
    setModalOpen(true);
  };

  const saveReagent = () => {
    form.validateFields().then((values) => {
      const payload = normalizeFormValues(values);
      const request = editingReagent
        ? apiClient.put<Reagent>(`/reagents/${editingReagent.id}`, payload)
        : apiClient.post<Reagent>("/reagents/", payload);

      request
        .then((response) => {
          if (editingReagent && response.data.adjustment_record_created) {
            message.success("试剂信息已更新，库存校正记录已生成");
          } else {
            message.success(editingReagent ? "试剂已更新" : "试剂已新增");
          }
          setModalOpen(false);
          setEditingReagent(null);
          form.resetFields();
          loadCategories();
          loadReagents();
        })
        .catch((error) => message.error(getApiError(error, editingReagent ? "更新试剂失败" : "新增试剂失败")));
    });
  };

  const deleteReagent = (reagent: Reagent) => {
    apiClient
      .delete(`/reagents/${reagent.id}`)
      .then(() => {
        message.success("试剂已删除");
        loadCategories();
        loadReagents();
      })
      .catch((error) => message.error(getApiError(error, "删除试剂失败")));
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          试剂管理
        </Typography.Title>
        {canManageReagent && (
          <Button type="primary" onClick={openCreateModal}>
            新增试剂
          </Button>
        )}
      </Space>

      <Card size="small">
        <Space wrap style={{ marginBottom: 12 }}>
          <Input.Search
            allowClear
            placeholder="中文名 / 英文名 / CAS号"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={(value) => {
              setKeyword(value);
              loadReagents(value, category);
            }}
            style={{ width: 320 }}
          />
          <Select
            allowClear
            placeholder="分类筛选"
            value={category}
            onChange={(value) => {
              setCategory(value);
              loadReagents(keyword, value);
            }}
            style={{ width: 180 }}
            options={categories.map((item) => ({ label: item, value: item }))}
          />
          <Button onClick={() => loadReagents()}>刷新</Button>
        </Space>

        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={reagents}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "ID", dataIndex: "id", width: 70 },
            { title: "中文名", dataIndex: "name_cn", width: 180 },
            { title: "英文名", dataIndex: "name_en", width: 300, ellipsis: true },
            { title: "分类", dataIndex: "category", width: 120 },
            {
              title: "当前库存",
              width: 120,
              render: (_, record: Reagent) => {
                const isLowStock = record.current_quantity <= record.warning_threshold;
                return (
                  <Space size={6}>
                    <span>{record.current_quantity}</span>
                    {isLowStock && <Tag color="red">低库存</Tag>}
                  </Space>
                );
              },
            },
            { title: "预警阈值", dataIndex: "warning_threshold", width: 120 },
            { title: "单位", dataIndex: "unit", width: 80 },
            { title: "纯度等级", dataIndex: "purity_grade", width: 100 },
            {
              title: "操作",
              width: 150,
              fixed: "right",
              render: (_, record: Reagent) => {
                if (!canManageReagent && !canDeleteReagent) {
                  return <Typography.Text type="secondary">无</Typography.Text>;
                }

                return (
                  <Space size={8}>
                    {canManageReagent && (
                      <Button size="small" onClick={() => openEditModal(record)}>
                        编辑
                      </Button>
                    )}
                    {canDeleteReagent && (
                      <Popconfirm title="确认删除该试剂？" okText="删除" cancelText="取消" onConfirm={() => deleteReagent(record)}>
                        <Button size="small" danger>
                          删除
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                );
              },
            },
          ]}
          scroll={{ x: 1350 }}
        />
      </Card>

      <Modal
        title={editingReagent ? "编辑试剂" : "新增试剂"}
        open={modalOpen}
        onOk={saveReagent}
        onCancel={() => setModalOpen(false)}
        width={720}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ unit: "瓶", current_quantity: 0, warning_threshold: 10 }}
        >
          <Space direction="vertical" style={{ width: "100%" }} size={0}>
            <Space style={{ width: "100%" }} align="start">
              <Form.Item
                name="name_cn"
                label="试剂中文名"
                rules={[{ required: true, message: "请输入试剂中文名" }]}
                style={{ width: 320 }}
              >
                <Input />
              </Form.Item>
              <Form.Item name="name_en" label="试剂英文名" style={{ width: 320 }}>
                <Input />
              </Form.Item>
            </Space>
            <Space style={{ width: "100%" }} align="start">
              <Form.Item name="cas_no" label="CAS号" style={{ width: 320 }}>
                <Input />
              </Form.Item>
              <Form.Item name="category" label="分类" style={{ width: 320 }}>
                <Input />
              </Form.Item>
            </Space>
            <Space style={{ width: "100%" }} align="start">
              <Form.Item name="specification" label="规格" style={{ width: 320 }}>
                <Input />
              </Form.Item>
              <Form.Item name="unit" label="单位" rules={[{ required: true, message: "请输入单位" }]} style={{ width: 320 }}>
                <Input />
              </Form.Item>
            </Space>
            <Space style={{ width: "100%" }} align="start">
              <Form.Item name="current_quantity" label="当前库存" style={{ width: 320 }}>
                <InputNumber style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="warning_threshold" label="预警阈值" style={{ width: 320 }}>
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            </Space>
            <Space style={{ width: "100%" }} align="start">
              <Form.Item name="location" label="存放位置" style={{ width: 320 }}>
                <Input />
              </Form.Item>
              <Form.Item name="supplier" label="供应商" style={{ width: 320 }}>
                <Input />
              </Form.Item>
            </Space>
            <Space style={{ width: "100%" }} align="start">
              <Form.Item name="hazard_level" label="危险等级" style={{ width: 320 }}>
                <Input />
              </Form.Item>
              <Form.Item name="expiry_date" label="有效期" style={{ width: 320 }}>
                <Input type="date" />
              </Form.Item>
            </Space>
            <Form.Item name="msds_url" label="MSDS 地址">
              <Input />
            </Form.Item>
            <Form.Item name="remark" label="备注">
              <Input.TextArea rows={3} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Space>
  );
}
