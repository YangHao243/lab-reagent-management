import { Text, View } from "@tarojs/components";
import { API_BASE_URL } from "../../utils/request";

export default function Profile() {
  return (
    <View className="page">
      <Text className="page-title">个人中心</Text>
      <Text className="page-subtitle">当前阶段先展示小程序本地配置，登录和权限后续再接入。</Text>

      <View className="panel">
        <Text className="panel-title">后端 API 地址</Text>
        <Text className="muted-text">{API_BASE_URL}</Text>
      </View>

      <View className="panel">
        <Text className="panel-title">登录状态</Text>
        <Text className="muted-text">未登录</Text>
      </View>
    </View>
  );
}
