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

type TimeSeriesPoint = {
  date: string;
  inbound_count: number;
  outbound_count: number;
  inbound_quantity: number;
  outbound_quantity: number;
};

type TimeSeriesReport = {
  period: "monthly";
  current: string;
  series: TimeSeriesPoint[];
};

type TopConsumed = {
  reagent_id: number;
  name_cn: string;
  unit?: string | null;
  out_count: number;
  total_consumed: number;
};

function pad2(value: number) {
  return String(value).padStart(2, "0");
}

function getYearRange(year: number) {
  return {
    start_date: `${year}-01-01`,
    end_date: `${year}-12-31`,
  };
}

export default function Reports() {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [summary, setSummary] = useState<Summary>({});
  const [series, setSeries] = useState<TimeSeriesPoint[]>([]);
  const [topRows, setTopRows] = useState<TopConsumed[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadReports = async (nextYear = year) => {
    setLoading(true);
    setError("");
    try {
      const range = getYearRange(nextYear);
      const [summaryData, seriesData, topData] = await Promise.all([
        request<Summary>({ url: "/reports/summary" }),
        request<TimeSeriesReport>({
          url: "/reports/timeseries",
          params: { period: "monthly", year: nextYear },
        }),
        request<TopConsumed[]>({
          url: "/reports/top-consumed",
          params: { ...range, limit: 10 },
        }),
      ]);
      setSummary(summaryData);
      setSeries(seriesData.series);
      setTopRows(topData);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "报表数据加载失败";
      setError(message);
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
      Taro.stopPullDownRefresh();
    }
  };

  useDidShow(() => {
    loadReports();
  });

  usePullDownRefresh(() => {
    loadReports();
  });

  const changeYear = (offset: number) => {
    const nextYear = year + offset;
    setYear(nextYear);
    loadReports(nextYear);
  };

  const annualInboundQuantity = series.reduce((total, item) => total + item.inbound_quantity, 0);
  const annualOutboundQuantity = series.reduce((total, item) => total + item.outbound_quantity, 0);
  const maxMonthlyCount = Math.max(
    1,
    ...series.map((item) => Math.max(item.inbound_count, item.outbound_count)),
  );
  const maxConsumed = Math.max(1, ...topRows.map((item) => item.total_consumed));

  const summaryCards = [
    { label: "试剂总数", value: summary.reagent_total ?? summary.total_reagents ?? 0 },
    { label: "低库存", value: summary.low_stock_count ?? 0 },
    { label: "流水总数", value: summary.total_inventory_records ?? 0 },
    { label: "本月出库", value: summary.month_out_count ?? 0 },
  ];

  return (
    <View className="page reports-page">
      <Text className="page-title">报表统计</Text>
      <Text className="page-subtitle">移动端以概览、趋势条和消耗排行展示核心库存统计。</Text>

      <View className="year-card panel">
        <Button className="year-button" size="mini" onClick={() => changeYear(-1)}>
          上一年
        </Button>
        <Text className="year-text">{year}</Text>
        <Button className="year-button" size="mini" onClick={() => changeYear(1)}>
          下一年
        </Button>
      </View>

      {error ? (
        <View className="panel state-card">
          <Text className="state-title">加载失败</Text>
          <Text className="muted-text">{error}</Text>
          <Button className="state-action" loading={loading} onClick={() => loadReports()}>
            重试
          </Button>
        </View>
      ) : null}

      <View className="summary-grid">
        {summaryCards.map((item) => (
          <View className="summary-card" key={item.label}>
            <Text className="summary-value">{item.value}</Text>
            <Text className="summary-label">{item.label}</Text>
          </View>
        ))}
      </View>

      <View className="panel">
        <Text className="panel-title">年度出入库数量</Text>
        <View className="annual-row">
          <View className="annual-card in">
            <Text className="annual-value">{annualInboundQuantity}</Text>
            <Text className="annual-label">年度入库总量</Text>
          </View>
          <View className="annual-card out">
            <Text className="annual-value">{annualOutboundQuantity}</Text>
            <Text className="annual-label">年度出库总量</Text>
          </View>
        </View>
      </View>

      <View className="panel">
        <Text className="panel-title">月度入库 / 出库趋势</Text>
        {series.length === 0 && !loading ? (
          <Text className="muted-text">暂无趋势数据</Text>
        ) : (
          series.map((item) => {
            const month = Number(item.date.slice(5, 7));
            const inWidth = Math.max(4, (item.inbound_count / maxMonthlyCount) * 100);
            const outWidth = Math.max(4, (item.outbound_count / maxMonthlyCount) * 100);
            return (
              <View className="month-row" key={item.date}>
                <Text className="month-label">{pad2(month)}月</Text>
                <View className="bar-group">
                  <View className="bar-line">
                    <Text className="bar-name">入</Text>
                    <View className="bar-track">
                      <View className="bar-fill in" style={{ width: `${inWidth}%` }} />
                    </View>
                    <Text className="bar-value">{item.inbound_count}</Text>
                  </View>
                  <View className="bar-line">
                    <Text className="bar-name">出</Text>
                    <View className="bar-track">
                      <View className="bar-fill out" style={{ width: `${outWidth}%` }} />
                    </View>
                    <Text className="bar-value">{item.outbound_count}</Text>
                  </View>
                </View>
              </View>
            );
          })
        )}
      </View>

      <View className="panel">
        <Text className="panel-title">试剂使用排行</Text>
        {topRows.length === 0 && !loading ? (
          <Text className="muted-text">暂无出库消耗数据</Text>
        ) : (
          topRows.map((item, index) => {
            const width = Math.max(6, (item.total_consumed / maxConsumed) * 100);
            return (
              <View className="rank-row" key={item.reagent_id}>
                <View className="rank-header">
                  <Text className="rank-name">
                    {index + 1}. {item.name_cn}
                  </Text>
                  <Text className="rank-value">
                    {item.total_consumed} {item.unit || ""}
                  </Text>
                </View>
                <View className="rank-track">
                  <View className="rank-fill" style={{ width: `${width}%` }} />
                </View>
                <Text className="rank-meta">出库次数：{item.out_count}</Text>
              </View>
            );
          })
        )}
      </View>
    </View>
  );
}
