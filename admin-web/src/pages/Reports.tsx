import {
  Card,
  DatePicker,
  InputNumber,
  Segmented,
  Space,
  Spin,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import * as echarts from "echarts";
import { useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";

type ReportMode = "daily" | "monthly" | "yearly";

type TimeSeriesPoint = {
  date: string;
  inbound_count: number;
  outbound_count: number;
  inbound_quantity: number;
  outbound_quantity: number;
};

type TimeSeriesReport = {
  period: ReportMode;
  current: string;
  series: TimeSeriesPoint[];
};

type TopConsumed = {
  reagent_id: number;
  name_cn: string;
  unit: string;
  out_count: number;
  total_consumed: number;
};

type CategorySummary = {
  category: string;
  reagent_count: number;
  low_stock_count: number;
  total_quantity: number;
};

type ChartData = {
  labels: string[];
  rawLabels: string[];
  inCounts: number[];
  outCounts: number[];
  inQuantities: number[];
  outQuantities: number[];
};

const emptyChartData: ChartData = {
  labels: [],
  rawLabels: [],
  inCounts: [],
  outCounts: [],
  inQuantities: [],
  outQuantities: [],
};

const topConsumedColumns: ColumnsType<TopConsumed> = [
  { title: "试剂ID", dataIndex: "reagent_id", width: 90 },
  { title: "试剂", dataIndex: "name_cn" },
  { title: "出库次数", dataIndex: "out_count", width: 110 },
  {
    title: "消耗量",
    width: 120,
    render: (_, record) => `${record.total_consumed} ${record.unit}`,
  },
];

function getApiError(error: unknown, fallback: string) {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail ===
      "string"
  ) {
    return (error as { response: { data: { detail: string } } }).response.data.detail;
  }
  return fallback;
}

function pad2(value: number) {
  return String(value).padStart(2, "0");
}

function formatDate(value: Date) {
  return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
}

function getMonthRange(value: Date) {
  const firstDay = new Date(value.getFullYear(), value.getMonth(), 1);
  const lastDay = new Date(value.getFullYear(), value.getMonth() + 1, 0);
  return {
    start_date: formatDate(firstDay),
    end_date: formatDate(lastDay),
  };
}

function getYearRange(value: Date) {
  return {
    start_date: `${value.getFullYear()}-01-01`,
    end_date: `${value.getFullYear()}-12-31`,
  };
}

function getRollingYearRange(value: Date, years = 5) {
  const endYear = value.getFullYear();
  const startYear = endYear - years + 1;
  return {
    start_date: `${startYear}-01-01`,
    end_date: `${endYear}-12-31`,
  };
}

function getRange(mode: ReportMode, value: Date) {
  if (mode === "daily") {
    return getMonthRange(value);
  }
  if (mode === "monthly") {
    return getYearRange(value);
  }
  return getRollingYearRange(value);
}

function getDisplayLabel(mode: ReportMode, value: Date) {
  if (mode === "daily") {
    return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}`;
  }
  if (mode === "monthly") {
    return `${value.getFullYear()}`;
  }
  return `${value.getFullYear() - 4}-${value.getFullYear()}`;
}

function parsePickerDate(mode: ReportMode, dateString: string | string[]) {
  const text = Array.isArray(dateString) ? dateString[0] : dateString;
  if (!text) {
    return new Date();
  }

  const parts = text.split("-").map((item) => Number(item));
  if (mode === "daily") {
    return new Date(parts[0], parts[1] - 1, 1);
  }
  return new Date(parts[0], 0, 1);
}

function getPickerMode(mode: ReportMode) {
  if (mode === "daily") {
    return "month" as const;
  }
  return "year" as const;
}

function formatAxisLabel(mode: ReportMode, value: string) {
  if (mode === "daily") {
    const [, month, day] = value.split("-");
    return `${Number(month)}-${Number(day)}`;
  }
  if (mode === "monthly") {
    return `${Number(value.slice(5, 7))}月`;
  }
  return value;
}

function buildChartData(mode: ReportMode, report: TimeSeriesReport): ChartData {
  return {
    labels: report.series.map((item) => formatAxisLabel(mode, item.date)),
    rawLabels: report.series.map((item) => item.date),
    inCounts: report.series.map((item) => item.inbound_count),
    outCounts: report.series.map((item) => item.outbound_count),
    inQuantities: report.series.map((item) => item.inbound_quantity),
    outQuantities: report.series.map((item) => item.outbound_quantity),
  };
}

function hasMovementData(data: ChartData) {
  return [...data.inCounts, ...data.outCounts, ...data.inQuantities, ...data.outQuantities].some(
    (value) => value > 0,
  );
}

export default function Reports() {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [mode, setMode] = useState<ReportMode>("daily");
  const [selectedDate, setSelectedDate] = useState<Date>(() => new Date());
  const [chartData, setChartData] = useState<ChartData>(emptyChartData);
  const [topLimit, setTopLimit] = useState(10);
  const [topRows, setTopRows] = useState<TopConsumed[]>([]);
  const [categoryRows, setCategoryRows] = useState<CategorySummary[]>([]);
  const [loading, setLoading] = useState(false);

  // 根据统计维度加载后端时序接口，并转换为 ECharts 折线图数据。
  const loadReport = async (nextMode = mode, nextDate = selectedDate, nextLimit = topLimit) => {
    setLoading(true);
    try {
      const timeSeriesParams =
        nextMode === "daily"
          ? {
              period: nextMode,
              year: nextDate.getFullYear(),
              month: nextDate.getMonth() + 1,
            }
          : {
              period: nextMode,
              year: nextDate.getFullYear(),
            };

      const range = getRange(nextMode, nextDate);
      const [timeSeriesResponse, topResponse, categoryResponse] = await Promise.all([
        apiClient.get<TimeSeriesReport>("/reports/timeseries", {
          params: timeSeriesParams,
        }),
        apiClient.get<TopConsumed[]>("/reports/top-consumed", {
          params: { ...range, limit: nextLimit },
        }),
        apiClient.get<CategorySummary[]>("/reports/category-summary"),
      ]);

      setChartData(buildChartData(nextMode, timeSeriesResponse.data));
      setTopRows(topResponse.data);
      setCategoryRows(categoryResponse.data);
    } catch (error) {
      message.error(getApiError(error, "报表数据加载失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }

    chartInstance.current = echarts.init(chartRef.current);

    const resize = () => chartInstance.current?.resize();
    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    resizeObserver?.observe(chartRef.current);
    window.addEventListener("resize", resize);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", resize);
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartInstance.current) {
      return;
    }

    const isEmpty = !hasMovementData(chartData);
    chartInstance.current.setOption(
      {
        color: ["#0f766e", "#dc2626"],
        title: {
          show: isEmpty,
          text: "暂无出入库统计数据",
          left: "center",
          top: "middle",
          textStyle: {
            color: "#9ca3af",
            fontSize: 14,
            fontWeight: "normal",
          },
        },
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "line" },
          formatter: (params: unknown) => {
            const items = Array.isArray(params) ? params : [];
            const firstItem = items[0] as { dataIndex?: number } | undefined;
            const index = firstItem?.dataIndex ?? 0;
            const label = chartData.rawLabels[index] || chartData.labels[index] || "";
            return [
              `日期：${label}`,
              `入库次数：${chartData.inCounts[index] ?? 0}`,
              `出库次数：${chartData.outCounts[index] ?? 0}`,
              `入库数量：${chartData.inQuantities[index] ?? 0}`,
              `出库数量：${chartData.outQuantities[index] ?? 0}`,
            ].join("<br/>");
          },
        },
        legend: {
          top: 0,
          data: ["入库次数", "出库次数"],
        },
        grid: {
          top: 58,
          right: 24,
          bottom: 42,
          left: 56,
          containLabel: true,
        },
        xAxis: {
          type: "category",
          boundaryGap: false,
          data: chartData.labels,
          axisTick: { alignWithLabel: true },
        },
        yAxis: {
          type: "value",
          name: "次数",
          minInterval: 1,
          splitLine: {
            lineStyle: { type: "dashed" },
          },
        },
        series: [
          {
            name: "入库次数",
            type: "line",
            smooth: true,
            symbol: "circle",
            symbolSize: 7,
            data: chartData.inCounts,
            lineStyle: { width: 3 },
            areaStyle: { opacity: 0.08 },
          },
          {
            name: "出库次数",
            type: "line",
            smooth: true,
            symbol: "circle",
            symbolSize: 7,
            data: chartData.outCounts,
            lineStyle: { width: 3 },
            areaStyle: { opacity: 0.08 },
          },
        ],
      },
      { notMerge: true },
    );

    requestAnimationFrame(() => chartInstance.current?.resize());
  }, [chartData]);

  const handleModeChange = (value: ReportMode) => {
    setMode(value);
    loadReport(value, selectedDate, topLimit);
  };

  const handleDateChange = (dateString: string | string[]) => {
    const nextDate = parsePickerDate(mode, dateString);
    setSelectedDate(nextDate);
    loadReport(mode, nextDate, topLimit);
  };

  const handleTopLimitChange = (value: number | null) => {
    const nextLimit = value || 10;
    setTopLimit(nextLimit);
    loadReport(mode, selectedDate, nextLimit);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space align="center" style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          报表统计
        </Typography.Title>
        <Space>
          <Segmented
            value={mode}
            onChange={(value) => handleModeChange(value as ReportMode)}
            options={[
              { label: "日统计", value: "daily" },
              { label: "月统计", value: "monthly" },
              { label: "年统计", value: "yearly" },
            ]}
          />
          <DatePicker
            key={mode}
            picker={getPickerMode(mode)}
            onChange={(_, dateString) => handleDateChange(dateString)}
            allowClear={false}
          />
          <Typography.Text type="secondary">当前：{getDisplayLabel(mode, selectedDate)}</Typography.Text>
        </Space>
      </Space>

      <Card title="出入库统计图表" size="small">
        <Spin spinning={loading}>
          <div ref={chartRef} style={{ height: 340, minHeight: 320, width: "100%" }} />
        </Spin>
      </Card>

      <Card
        title="消耗 Top N"
        size="small"
        extra={
          <Space>
            <Typography.Text type="secondary">数量</Typography.Text>
            <InputNumber
              min={1}
              max={100}
              value={topLimit}
              onChange={handleTopLimitChange}
              style={{ width: 96 }}
            />
          </Space>
        }
      >
        <Table
          rowKey="reagent_id"
          size="small"
          loading={loading}
          dataSource={topRows}
          pagination={false}
          columns={topConsumedColumns}
        />
      </Card>

      <Card title="分类库存汇总" size="small">
        <Table
          rowKey="category"
          size="small"
          loading={loading}
          dataSource={categoryRows}
          pagination={false}
          columns={[
            { title: "分类", dataIndex: "category" },
            { title: "试剂数量", dataIndex: "reagent_count" },
            { title: "低库存数量", dataIndex: "low_stock_count" },
            { title: "总库存量", dataIndex: "total_quantity" },
          ]}
        />
      </Card>
    </Space>
  );
}
