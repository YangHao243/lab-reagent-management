import Taro, { useDidShow } from "@tarojs/taro";
import { Button, Input, Text, View } from "@tarojs/components";
import { useState } from "react";
import { API_BASE_URL } from "../../config";
import { clearAuth, getCurrentUser, login, type CurrentUser } from "../../utils/request";

export default function Profile() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<CurrentUser | undefined>();
  const [submitting, setSubmitting] = useState(false);

  useDidShow(() => {
    setUser(getCurrentUser());
  });

  const submitLogin = async () => {
    if (!username.trim() || !password) {
      Taro.showToast({ title: "请输入用户名和密码", icon: "none" });
      return;
    }

    setSubmitting(true);
    try {
      const result = await login(username.trim(), password);
      setUser(result.user);
      setPassword("");
      Taro.showToast({ title: "登录成功", icon: "success" });
      setTimeout(() => Taro.switchTab({ url: "/pages/index/index" }), 500);
    } catch (error) {
      const message = error instanceof Error ? error.message : "登录失败";
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setSubmitting(false);
    }
  };

  const logout = () => {
    clearAuth();
    setUser(undefined);
    setUsername("");
    setPassword("");
    Taro.showToast({ title: "已退出登录", icon: "none" });
  };

  return (
    <View className="page">
      <Text className="page-title">登录与设置</Text>
      <Text className="page-subtitle">小程序端复用后端账号体系，token 会保存在本机小程序存储中。</Text>

      <View className="panel">
        <Text className="panel-title">后端 API 地址</Text>
        <Text className="muted-text">{API_BASE_URL}</Text>
      </View>

      {user ? (
        <View className="panel">
          <Text className="panel-title">当前用户</Text>
          <Text className="muted-text">用户名：{user.username}</Text>
          <Text className="muted-text">角色：{user.role}</Text>
          <Button className="danger-button" onClick={logout}>
            退出登录
          </Button>
        </View>
      ) : (
        <View className="panel">
          <Text className="panel-title">账号登录</Text>
          <Text className="form-label">用户名</Text>
          <Input
            className="form-input"
            placeholder="请输入用户名"
            value={username}
            onInput={(event) => setUsername(event.detail.value)}
          />
          <Text className="form-label">密码</Text>
          <Input
            className="form-input"
            password
            placeholder="请输入密码"
            value={password}
            onInput={(event) => setPassword(event.detail.value)}
          />
          <Button className="primary-button" loading={submitting} onClick={submitLogin}>
            登录
          </Button>
        </View>
      )}

      <View className="panel">
        <Text className="panel-title">微信合法域名提醒</Text>
        <Text className="muted-text">
          使用真实微信小程序测试或发布时，需要在微信公众平台配置 request 合法域名为后端 Render 域名。
          开发者工具调试可临时勾选“不校验合法域名”。
        </Text>
      </View>
    </View>
  );
}
