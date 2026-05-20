import Taro from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { useEffect, useState } from "react";
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
};

type Reagent = {
  id: number;
  name_cn: string;
  category?: string;
  current_quantity: number;
  warning_threshold: number;
  unit?: string;
  location?: string;
};

type ActionItem = {
  title: string;
  url: string;
  selectReagentFirst?: boolean;
};

const defaultSummary: Summary = {
  reagent_total: 0,
  total_reagents: 0,
  low_stock_count: 0,
  today_in_count: 0,
  today_out_count: 0,
  month_in_count: 0,
  month_out_count: 0,
};

const actions: ActionItem[] = [
  { title: "试剂列表", url: "/pages/reagent-list/index" },
  { title: "入库", url: "/pages/reagent-list/index", selectReagentFirst: true },
  { title: "出库", url: "/pages/reagent-list/index", selectReagentFirst: true },
  { title: "报警", url: "/pages/alerts/index" },
  { title: "我的", url: "/pages/profile/index" },
];

function normalizeSummary(data: Summary): Required<Summary> {
  return {
    reagent_total: data.reagent_total ?? data.total_reagents ?? 0,
    total_reagents: data.total_reagents ?? data.reagent_total ?? 0,
    low_stock_count: data.low_stock_count ?? 0,
    today_in_count: data.today_in_count ?? 0,
    today_out_count: data.today_out_count ?? 0,
    month_in_count: data.month_in_count ?? 0,
    month_out_count: data.month_out_count ?? 0,
  };
}

export default function Index() {
  const [summary, setSummary] = useState<Summary>(defaultSummary);
  const [lowStock, setLowStock] = useState<Reagent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 首页加载库存总览和低库存试剂，方便实验室成员快速判断库存状态。
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
      const message = requestError instanceof Error ? requestError.message : "首页数据加载失败";
      setError(message);
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  const openAction = (item: ActionItem) => {
    if (item.selectReagentFirst) {
      Taro.showToast({ title: "请先选择试剂", icon: "none" });
    }
    Taro.navigateTo({ url: item.url });
  };

  const openReagentDetail = (id: number) => {
    Taro.navigateTo({ url: `/pages/reagent-detail/index?id=${id}` });
  };

  return (
    <View className="page index-page">
      <View className="hero">
        <Text className="hero-title">实验室试剂仓库管理</Text>
        <Text className="hero-subtitle">库存总览、出入库和报警信息集中查看</Text>
      </View>

      <View className="summary-grid">
        <View className="summary-card">
          <Text className="summary-value">{summary.reagent_total ?? summary.total_reagents ?? 0}</Text>
          <Text className="summary-label">试剂总数</Text>
        </View>
        <View className="summary-card warning">
          <Text className="summary-value">{summary.low_stock_count ?? 0}</Text>
          <Text className="summary-label">低库存数量</Text>
        </View>
        <View className="summary-card">
          <Text className="summary-value">{summary.today_in_count ?? 0}</Text>
          <Text className="summary-label">今日入库次数</Text>
        </View>
        <View className="summary-card">
          <Text className="summary-value">{summary.today_out_count ?? 0}</Text>
          <Text className="summary-label">今日出库次数</Text>
        </View>
      </View>

      <View className="action-grid">
        {actions.map((item) => (
          <Button className="action-button" key={item.title} onClick={() => openAction(item)}>
            {item.title}
          </Button>
        ))}
      </View>

      <View className="section-card">
        <View className="section-header">
          <Text className="section-title">低库存试剂</Text>
          <Button className="refresh-button" size="mini" loading={loading} onClick={loadDashboard}>
            刷新
          </Button>
        </View>

        {error && <Text className="error-text">{error}</Text>}

        {lowStock.length === 0 && !loading ? (
          <Text className="empty-text">暂无低库存试剂</Text>
        ) : (
          lowStock.slice(0, 6).map((item) => (
            <View className="reagent-row" key={item.id} onClick={() => openReagentDetail(item.id)}>
              <View>
                <Text className="reagent-name">{item.name_cn}</Text>
                <Text className="reagent-meta">
                  位置：{item.location || "未填写"}
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
