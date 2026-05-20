import {
  AlertOutlined,
  BarChartOutlined,
  CloudSyncOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  LogoutOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Result, Space, Spin, Tag, Typography } from "antd";
import type { MenuProps } from "antd";
import type { ReactNode } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import type { UserRole } from "./auth/storage";
import Alerts from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import InventoryRecords from "./pages/InventoryRecords";
import Login from "./pages/Login";
import ReagentList from "./pages/ReagentList";
import Reports from "./pages/Reports";
import TencentDocsSync from "./pages/TencentDocsSync";
import Users from "./pages/Users";

const { Header, Content, Sider } = Layout;

type AppMenuItem = {
  key: string;
  icon: ReactNode;
  label: string;
  roles?: UserRole[];
};

const menuConfig: AppMenuItem[] = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/reagents", icon: <DatabaseOutlined />, label: "试剂库存" },
  { key: "/inventory", icon: <FileTextOutlined />, label: "库存流水" },
  { key: "/alerts", icon: <AlertOutlined />, label: "报警事件" },
  { key: "/reports", icon: <BarChartOutlined />, label: "报表统计" },
  {
    key: "/tencent-docs",
    icon: <CloudSyncOutlined />,
    label: "腾讯文档同步",
    roles: ["manager", "admin", "superadmin"],
  },
  {
    key: "/users",
    icon: <TeamOutlined />,
    label: "用户管理",
    roles: ["admin", "superadmin"],
  },
];

function FullPageLoading() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Spin tip="正在验证登录状态..." />
    </div>
  );
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { loading, isAuthenticated } = useAuth();

  if (loading) {
    return <FullPageLoading />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

function RoleRoute({ roles, children }: { roles: UserRole[]; children: ReactNode }) {
  const navigate = useNavigate();
  const { hasRole } = useAuth();

  if (!hasRole(...roles)) {
    return (
      <Result
        status="403"
        title="无权限访问"
        subTitle="当前用户无权限访问该页面。"
        extra={
          <Button type="primary" onClick={() => navigate("/dashboard", { replace: true })}>
            返回仪表盘
          </Button>
        }
      />
    );
  }

  return <>{children}</>;
}

function LoginRoute() {
  const { loading, isAuthenticated } = useAuth();

  if (loading) {
    return <FullPageLoading />;
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Login />;
}

function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, hasRole, logout } = useAuth();
  const selectedKey = `/${location.pathname.split("/")[1] || "dashboard"}`;

  const menuItems: MenuProps["items"] = menuConfig
    .filter((item) => !item.roles || hasRole(...item.roles))
    .map((item) => ({
      key: item.key,
      icon: item.icon,
      label: <Link to={item.key}>{item.label}</Link>,
    }));

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <Layout style={{ minHeight: "100vh", background: "#eef2f7" }}>
      <Sider width={224} theme="dark">
        <div style={{ height: 56, display: "flex", alignItems: "center", padding: "0 20px" }}>
          <Typography.Text strong style={{ color: "#fff", fontSize: 16 }}>
            试剂仓库管理
          </Typography.Text>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]} items={menuItems} />
      </Sider>
      <Layout>
        <Header
          style={{
            height: 56,
            background: "#fff",
            borderBottom: "1px solid #dde3ea",
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            实验室化学试剂仓库管理系统
          </Typography.Title>
          <Space>
            <Typography.Text>{user?.full_name || user?.username}</Typography.Text>
            <Tag color="blue">{user?.role}</Tag>
            <Button icon={<LogoutOutlined />} onClick={handleLogout}>
              退出登录
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/reagents" element={<ReagentList />} />
            <Route path="/inventory" element={<InventoryRecords />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/reports" element={<Reports />} />
            <Route
              path="/tencent-docs"
              element={
                <RoleRoute roles={["manager", "admin", "superadmin"]}>
                  <TencentDocsSync />
                </RoleRoute>
              }
            />
            <Route
              path="/users"
              element={
                <RoleRoute roles={["admin", "superadmin"]}>
                  <Users />
                </RoleRoute>
              }
            />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AdminLayout />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
