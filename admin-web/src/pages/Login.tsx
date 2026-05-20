import { Button, Card, Form, Input, Typography, message } from "antd";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

type LoginFormValues = {
  username: string;
  password: string;
};

export default function Login() {
  const navigate = useNavigate();
  const { isAuthenticated, login } = useAuth();
  const [form] = Form.useForm<LoginFormValues>();

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleLogin = async () => {
    const values = await form.validateFields();
    try {
      await login(values.username, values.password);
      message.success("登录成功");
      navigate("/dashboard", { replace: true });
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      message.error(typeof detail === "string" ? detail : "登录失败，请检查用户名和密码");
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#eef2f7",
        padding: 24,
      }}
    >
      <Card style={{ width: 420 }} styles={{ body: { padding: 32 } }}>
        <Typography.Title level={3} style={{ textAlign: "center", marginBottom: 8 }}>
          实验室化学试剂仓库管理系统
        </Typography.Title>
        <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginBottom: 28 }}>
          请使用系统账号登录
        </Typography.Text>
        <Form form={form} layout="vertical" onFinish={handleLogin}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input autoComplete="username" placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password autoComplete="current-password" placeholder="请输入密码" />
          </Form.Item>
          <Button type="primary" block htmlType="submit">
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
