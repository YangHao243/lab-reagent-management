import Taro, { useRouter } from "@tarojs/taro";
import { Button, Text, View } from "@tarojs/components";
import { useEffect, useState } from "react";
import { request } from "../../utils/request";
import { formatShortDate } from "../../utils/time";
import "./index.scss";

type Reagent = {
  id: number;
  name_cn: string;
  standard_name?: string | null;
  alias_name?: string | null;
  name_en?: string | null;
  cas_no?: string | null;
  category?: string | null;
  specification?: string | null;
  unit?: string | null;
  current_quantity: number;
  warning_threshold: number;
  location?: string | null;
  supplier?: string | null;
  hazard_level?: string | null;
  purity_grade?: string | null;
  expiry_date?: string | null;
  remark?: string | null;
};

function showValue(value?: string | number | null) {
  if (value === undefined || value === null || value === "") {
    return "-";
  }
  return String(value);
}

export default function ReagentDetail() {
  const router = useRouter();
  const reagentId = Number(router.params.reagent_id || router.params.id || 0);
  const [reagent, setReagent] = useState<Reagent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadReagentDetail = async () => {
    if (!reagentId) {
      setError("缺少试剂 ID");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const data = await request<Reagent>({ url: `/reagents/${reagentId}` });
      setReagent(data);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "试剂详情加载失败";
      setError(message);
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

  const isLowStock =
    reagent !== null && reagent.current_quantity <= reagent.warning_threshold;

  const fields = reagent
    ? [
        ["标准名称", reagent.standard_name],
        ["别名", reagent.alias_name],
        ["英文名", reagent.name_en],
        ["CAS 号", reagent.cas_no],
        ["分类", reagent.category],
        ["规格", reagent.specification],
        ["纯度等级", reagent.purity_grade],
        ["存放位置", reagent.location],
        ["危险等级", reagent.hazard_level],
        ["供应商", reagent.supplier],
        ["有效期", reagent.expiry_date ? formatShortDate(reagent.expiry_date) : "-"],
        ["备注", reagent.remark],
      ]
    : [];

  return (
    <View className="page reagent-detail-page">
      <Text className="page-title">试剂详情</Text>
      <Text className="page-subtitle">查看试剂基础信息和实时库存状态。</Text>

      {error ? (
        <View className="panel state-card">
          <Text className="state-title">加载失败</Text>
          <Text className="muted-text">{error}</Text>
          <Button className="state-action" loading={loading} onClick={loadReagentDetail}>
            重试
          </Button>
        </View>
      ) : null}

      {reagent ? (
        <>
          <View className={isLowStock ? "stock-panel low" : "stock-panel"}>
            <View className="stock-header">
              <View className="name-block">
                <Text className="reagent-name">{reagent.name_cn}</Text>
                <Text className="reagent-subtitle">{reagent.category || "未分类"}</Text>
              </View>
              {isLowStock ? <Text className="tag tag-red">低库存</Text> : <Text className="tag tag-green">正常</Text>}
            </View>
            <View className="two-column">
              <View className="stock-item">
                <Text className="stock-label">当前库存</Text>
                <Text className={isLowStock ? "stock-value danger" : "stock-value"}>
                  {reagent.current_quantity} {reagent.unit || ""}
                </Text>
              </View>
              <View className="stock-item">
                <Text className="stock-label">预警阈值</Text>
                <Text className="stock-value">
                  {reagent.warning_threshold} {reagent.unit || ""}
                </Text>
              </View>
            </View>
          </View>

          <View className="panel">
            {fields.map(([label, value]) => (
              <View className="detail-row" key={label}>
                <Text className="detail-label">{label}</Text>
                <Text className="detail-value">{showValue(value)}</Text>
              </View>
            ))}
          </View>

          <View className="action-row">
            <Button className="primary-button action-button" onClick={() => openInventoryPage("in")}>
              入库
            </Button>
            <Button className="danger-button action-button" onClick={() => openInventoryPage("out")}>
              出库
            </Button>
          </View>
        </>
      ) : !loading ? (
        <View className="panel state-card">
          <Text className="muted-text">暂无试剂详情</Text>
        </View>
      ) : null}
    </View>
  );
}
