import Taro, { useRouter } from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { useEffect, useState } from "react";
import { request } from "../../utils/request";
import "./index.scss";

type Reagent = {
  id: number;
  name_cn: string;
  standard_name?: string;
  name_en?: string;
  cas_no?: string;
  category?: string;
  specification?: string;
  unit?: string;
  current_quantity: number;
  warning_threshold: number;
  location?: string;
  supplier?: string;
  hazard_level?: string;
  expiry_date?: string;
  msds_url?: string;
  remark?: string;
  created_at?: string;
  updated_at?: string;
};

function formatValue(value?: string | number | null) {
  if (value === undefined || value === null || value === "") {
    return "未填写";
  }
  return String(value);
}

export default function ReagentDetail() {
  const router = useRouter();
  const reagentId = Number(router.params.reagent_id || router.params.id);
  const [reagent, setReagent] = useState<Reagent | null>(null);
  const [loading, setLoading] = useState(false);

  // 根据列表页传入的 reagent_id 加载完整试剂详情。
  const loadReagentDetail = async () => {
    if (!reagentId) {
      Taro.showToast({ title: "缺少试剂 ID", icon: "none" });
      return;
    }

    setLoading(true);
    try {
      const data = await request<Reagent>({ url: `/reagents/${reagentId}` });
      setReagent(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "试剂详情加载失败";
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReagentDetail();
  }, [reagentId]);

  const openInventoryPage = (type: "in" | "out") => {
    const url = type === "in" ? "/pages/inventory-in/index" : "/pages/inventory-out/index";
    Taro.navigateTo({ url: `${url}?reagent_id=${reagentId}` });
  };

  const fields = reagent
    ? [
        ["中文名", reagent.name_cn],
        ["标准名称", reagent.standard_name],
        ["分类", reagent.category],
        ["当前库存", `${reagent.current_quantity} ${reagent.unit || ""}`],
        ["预警阈值", `${reagent.warning_threshold} ${reagent.unit || ""}`],
        ["存放位置", reagent.location],
        ["危险等级", reagent.hazard_level],
        ["备注", reagent.remark],
      ]
    : [];

  const isLowStock =
    reagent !== null && reagent.current_quantity <= reagent.warning_threshold;

  return (
    <View className="page">
      <Text className="page-title">试剂详情</Text>
      <Text className="page-subtitle">查看试剂基础信息，并可快速进入入库或出库操作。</Text>

      {!reagent && !loading ? (
        <View className="panel">
          <Text className="muted-text">暂无详情数据</Text>
        </View>
      ) : (
        <View className="panel">
          <Text className="panel-title">{reagent?.name_cn || "加载中..."}</Text>
          {isLowStock && (
            <View className="low-stock-notice">
              <Text className="low-stock-text">低库存提醒：当前库存已低于或等于预警阈值</Text>
            </View>
          )}
          {fields.map(([label, value]) => (
            <View key={label}>
              <Text className="form-label">{label}</Text>
              <Text>{formatValue(value)}</Text>
            </View>
          ))}
        </View>
      )}

      <Button className="primary-button" onClick={() => openInventoryPage("in")}>
        入库
      </Button>
      <Button className="danger-button" onClick={() => openInventoryPage("out")}>
        出库
      </Button>
      <Button onClick={() => Taro.navigateBack()}>返回</Button>
    </View>
  );
}
