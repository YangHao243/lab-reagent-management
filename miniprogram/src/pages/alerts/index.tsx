import Taro, { useDidShow, usePullDownRefresh } from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { useState } from "react";
import { getCurrentUser, request } from "../../utils/request";
import { formatBeijingTime } from "../../utils/time";
import "./index.scss";

type AlertFilter = "unresolved" | "resolved" | "all";

type LowStockReagent = {
  id: number;
  name_cn: string;
  current_quantity: number;
  warning_threshold: number;
  unit?: string | null;
  location?: string | null;
};

type AlertEvent = {
  id: number;
  year_display_id?: number;
  reagent_id: number;
  alert_type: string;
  level: string;
  message: string;
  is_resolved: boolean;
  resolved_at?: string | null;
  created_at: string;
};

const filters: Array<{ label: string; value: AlertFilter }> = [
  { label: "未处理", value: "unresolved" },
  { label: "已处理", value: "resolved" },
  { label: "全部", value: "all" },
];

function canHandleAlerts() {
  const role = getCurrentUser()?.role;
  return role === "manager" || role === "admin" || role === "superadmin";
}

export default function Alerts() {
  const [filter, setFilter] = useState<AlertFilter>("unresolved");
  const [lowStock, setLowStock] = useState<LowStockReagent[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resolvingId, setResolvingId] = useState<number | null>(null);

  const loadAlerts = async (nextFilter = filter) => {
    setLoading(true);
    setError("");

    try {
      const params =
        nextFilter === "all"
          ? {}
          : { is_resolved: nextFilter === "resolved" };
      const [lowStockData, eventData] = await Promise.all([
        request<LowStockReagent[]>({ url: "/alerts/low-stock" }),
        request<AlertEvent[]>({ url: "/alerts/events", params }),
      ]);
      setLowStock(lowStockData);
      setEvents(eventData);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "报警数据加载失败";
      setError(message);
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
      Taro.stopPullDownRefresh();
    }
  };

  useDidShow(() => {
    loadAlerts();
  });

  usePullDownRefresh(() => {
    loadAlerts();
  });

  const changeFilter = (nextFilter: AlertFilter) => {
    setFilter(nextFilter);
    loadAlerts(nextFilter);
  };

  const resolveAlert = async (alertId: number) => {
    setResolvingId(alertId);
    try {
      await request<AlertEvent>({ url: `/alerts/events/${alertId}/resolve`, method: "PUT" });
      Taro.showToast({ title: "已标记处理", icon: "success" });
      loadAlerts();
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "处理报警失败";
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <View className="page alerts-page">
      <Text className="page-title">报警事件</Text>
      <Text className="page-subtitle">查看低库存和系统报警，移动端适合快速确认库存风险。</Text>

      <View className="filter-row">
        {filters.map((item) => (
          <Text
            className={filter === item.value ? "filter-chip active" : "filter-chip"}
            key={item.value}
            onClick={() => changeFilter(item.value)}
          >
            {item.label}
          </Text>
        ))}
      </View>

      {error ? (
        <View className="panel state-card">
          <Text className="state-title">加载失败</Text>
          <Text className="muted-text">{error}</Text>
          <Button className="state-action" loading={loading} onClick={() => loadAlerts()}>
            重试
          </Button>
        </View>
      ) : null}

      <View className="section-title-row">
        <Text className="section-title">低库存提醒</Text>
        <Text className="section-count">{lowStock.length} 项</Text>
      </View>

      {lowStock.length === 0 && !loading ? (
        <View className="panel small-empty">
          <Text className="muted-text">暂无低库存试剂</Text>
        </View>
      ) : (
        lowStock.slice(0, 8).map((item) => (
          <View className="low-stock-card" key={item.id}>
            <View className="card-header">
              <Text className="alert-name">{item.name_cn}</Text>
              <Text className="tag tag-red">低库存</Text>
            </View>
            <Text className="alert-line">
              当前库存：{item.current_quantity} {item.unit || ""}，阈值：{item.warning_threshold} {item.unit || ""}
            </Text>
            <Text className="alert-line">位置：{item.location || "未填写"}</Text>
          </View>
        ))
      )}

      <View className="section-title-row">
        <Text className="section-title">报警流水</Text>
        <Text className="section-count">{events.length} 条</Text>
      </View>

      {events.length === 0 && !loading ? (
        <View className="panel state-card">
          <Text className="muted-text">当前筛选条件下暂无报警事件</Text>
        </View>
      ) : (
        events.map((item) => (
          <View className="event-card" key={item.id}>
            <View className="card-header">
              <View>
                <Text className="event-title">{item.alert_type}</Text>
                <Text className="event-time">{formatBeijingTime(item.created_at)}</Text>
              </View>
              <Text className={item.is_resolved ? "tag tag-green" : "tag tag-orange"}>
                {item.is_resolved ? "已处理" : "未处理"}
              </Text>
            </View>
            <Text className="event-message">{item.message}</Text>
            {!item.is_resolved && canHandleAlerts() ? (
              <Button
                className="resolve-button"
                size="mini"
                loading={resolvingId === item.id}
                onClick={() => resolveAlert(item.id)}
              >
                标记已处理
              </Button>
            ) : null}
          </View>
        ))
      )}
    </View>
  );
}
