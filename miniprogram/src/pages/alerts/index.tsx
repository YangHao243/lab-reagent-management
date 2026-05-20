import { Text, View } from "@tarojs/components";

export default function Alerts() {
  return (
    <View className="page">
      <Text className="page-title">库存报警</Text>
      <Text className="page-subtitle">这里将展示低库存、即将过期等报警信息。</Text>

      <View className="panel">
        <Text className="panel-title">低库存提醒</Text>
        <Text className="muted-text">后续接入 GET /alerts/low-stock。</Text>
      </View>

      <View className="panel">
        <Text className="panel-title">过期提醒</Text>
        <Text className="muted-text">后续接入 GET /alerts/expiring。</Text>
      </View>
    </View>
  );
}
