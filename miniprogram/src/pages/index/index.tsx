import Taro, { useDidShow, usePullDownRefresh } from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { useState } from "react";
import { request } from "../../utils/request";
import "./index.scss";

type Summary = {
  reagent_total?: number;
  total_reagents?: number;
  low_stock_count?: number;
  today_in_count?: number;
  today_out_count?: number;
  month_in_count?: number;
  month_out_count?: number;
  total_inventory_records?: number;
};

type Reagent = {
  id: number;
  name_cn: string;
  category?: string | null;
  current_quantity: number;
  warning_threshold: number;
  unit?: string | null;
  location?: string | null;
};

const defaultSummary: Required<Summary> = {
  reagent_total: 0,
  total_reagents: 0,
  low_stock_count: 0,
  today_in_count: 0,
  today_out_count: 0,
  month_in_count: 0,
  month_out_count: 0,
  total_inventory_records: 0,
};

function normalizeSummary(data: Summary): Required<Summary> {
  const reagentTotal = data.reagent_total ?? data.total_reagents ?? 0;
  return {
    reagent_total: reagentTotal,
    total_reagents: reagentTotal,
    low_stock_count: data.low_stock_count ?? 0,
    today_in_count: data.today_in_count ?? 0,
    today_out_count: data.today_out_count ?? 0,
    month_in_count: data.month_in_count ?? 0,
    month_out_count: data.month_out_count ?? 0,
    total_inventory_records: data.total_inventory_records ?? 0,
  };
}

export default function Index() {
  const [summary, setSummary] = useState<Required<Summary>>(defaultSummary);
  const [lowStock, setLowStock] = useState<Reagent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadDashboard = async () => {
    setLoading(true);
    setError("");

    try {
      const [summaryData, lowStockData] = await Promise.all([
        request<Summary>({ url: "/reports/summary" }),
        request<Reagent[]>({ url: "/alerts/low-stock" }),
      ]);
      setSummary(normalizeSummary(summaryData));
      setLowStock(lowStockData);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "仪表盘数据加载失败";
      setError(message);
    } finally {
      setLoading(false);
      Taro.stopPullDownRefresh();
    }
  };

  useDidShow(() => {
    loadDashboard();
  });

  usePullDownRefresh(() => {
    loadDashboard();
  });

  const stats = [
    { label: "试剂总数", value: summary.reagent_total, tone: "blue" },
    { label: "低库存", value: summary.low_stock_count, tone: "red" },
    { label: "今日入库", value: summary.today_in_count, tone: "green" },
    { label: "今日出库", value: summary.today_out_count, tone: "orange" },
    { label: "本月入库", value: summary.month_in_count, tone: "green" },
    { label: "本月出库", value: summary.month_out_count, tone: "orange" },
  ];

  const openReagentDetail = (id: number) => {
    Taro.navigateTo({ url: `/pages/reagent-detail/index?reagent_id=${id}` });
  };

  return (
    <View className="page dashboard-page">
      <View className="hero">
        <Text className="hero-eyebrow">Lab Reagent</Text>
        <Text className="hero-title">实验室试剂仓库管理</Text>
        <Text className="hero-subtitle">查看库存总览、低库存提醒和近期出入库状态</Text>
      </View>

      {error ? (
        <View className="panel state-card">
          <Text className="state-title">数据加载失败</Text>
          <Text className="muted-text">{error}</Text>
          <Button className="state-action" loading={loading} onClick={loadDashboard}>
            重试
          </Button>
        </View>
      ) : null}

      <View className="summary-grid">
        {stats.map((item) => (
          <View className={`summary-card ${item.tone}`} key={item.label}>
            <Text className="summary-value">{item.value}</Text>
            <Text className="summary-label">{item.label}</Text>
          </View>
        ))}
      </View>

      <View className="section-card">
        <View className="section-header">
          <Text className="section-title">低库存试剂</Text>
          <Button className="refresh-button" size="mini" loading={loading} onClick={loadDashboard}>
            刷新
          </Button>
        </View>

        {lowStock.length === 0 && !loading ? (
          <View className="empty-box">
            <Text className="muted-text">暂无低库存试剂</Text>
          </View>
        ) : (
          lowStock.slice(0, 8).map((item) => (
            <View className="reagent-row" key={item.id} onClick={() => openReagentDetail(item.id)}>
              <View className="reagent-main">
                <Text className="reagent-name">{item.name_cn}</Text>
                <Text className="reagent-meta">
                  {item.category || "未分类"} · {item.location || "未填写位置"}
                </Text>
              </View>
              <View className="stock-box">
                <Text className="stock-value">
                  {item.current_quantity} {item.unit || ""}
                </Text>
                <Text className="stock-threshold">
                  阈值 {item.warning_threshold} {item.unit || ""}
                </Text>
              </View>
            </View>
          ))
        )}
      </View>
    </View>
  );
}
