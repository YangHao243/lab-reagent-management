import { Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type User = {
  id: number;
  username: string;
  full_name?: string;
  role: string;
  email?: string;
  phone?: string;
  is_active: boolean;
  created_at: string;
};

export default function Users() {
  const { user } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const loadUsers = () => {
    apiClient
      .get<User[]>("/users/")
      .then((response) => setUsers(response.data))
      .catch(() => message.warning("用户列表加载失败"));
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const registerUser = () => {
    form.validateFields().then((values) => {
      apiClient
        .post("/users/register", values)
        .then(() => {
          message.success("用户已创建");
          setOpen(false);
          form.resetFields();
          loadUsers();
        })
        .catch((error) => {
          const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
          message.error(typeof detail === "string" ? detail : "创建用户失败");
        });
    });
  };

  const disableUser = (id: number) => {
    apiClient
      .delete(`/users/${id}`)
      .then(() => {
        message.success("用户已禁用");
        loadUsers();
      })
      .catch((error) => {
        const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
        message.error(typeof detail === "string" ? detail : "禁用用户失败");
      });
  };

  const roleOptions = [
    { label: "member", value: "member" },
    { label: "admin", value: "admin" },
    { label: "manager", value: "manager" },
    ...(user?.role === "superadmin" ? [{ label: "superadmin", value: "superadmin" }] : []),
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          用户管理
        </Typography.Title>
        <Button type="primary" onClick={() => setOpen(true)}>
          新增用户
        </Button>
      </Space>
      <Card size="small">
        <Table
          rowKey="id"
          size="small"
          dataSource={users}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "ID", dataIndex: "id", width: 72 },
            { title: "用户名", dataIndex: "username" },
            { title: "姓名", dataIndex: "full_name" },
            { title: "角色", dataIndex: "role" },
            { title: "邮箱", dataIndex: "email" },
            { title: "手机号", dataIndex: "phone" },
            {
              title: "状态",
              dataIndex: "is_active",
              render: (value: boolean) => (value ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>),
            },
            {
              title: "操作",
              width: 96,
              render: (_, record) => (
                <Button
                  size="small"
                  disabled={!record.is_active || record.id === user?.id || (record.role === "superadmin" && user?.role !== "superadmin")}
                  onClick={() => disableUser(record.id)}
                >
                  禁用
                </Button>
              ),
            },
          ]}
        />
      </Card>
      <Modal title="新增用户" open={open} onOk={registerUser} onCancel={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ role: "member" }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 6, message: "请输入至少 6 位密码" }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="full_name" label="姓名">
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select
              options={roleOptions}
            />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
