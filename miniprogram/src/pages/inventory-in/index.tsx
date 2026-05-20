import Taro, { useRouter } from "@tarojs/taro";
import { Button, Input, Text, Textarea, View } from "@tarojs/components";
import { useEffect, useState } from "react";
import { request } from "../../utils/request";
import "./index.scss";

type StockInfo = {
  reagent_id: number;
  name_cn: string;
  category?: string;
  current_quantity: number;
  unit?: string;
  warning_threshold: number;
  low_stock: boolean;
  location?: string;
  hazard_level?: string;
  updated_at?: string;
};

type InventoryResponse = {
  id: number;
  reagent_id: number;
  reagent_name?: string;
  operation_type: string;
  quantity_change: number;
  before_quantity: number;
  after_quantity: number;
  unit?: string;
  low_stock?: boolean;
  warning_threshold?: number;
  created_at: string;
};

function formatValue(value?: string | number | null) {
  if (value === undefined || value === null || value === "") {
    return "未填写";
  }
  return String(value);
}

export default function InventoryIn() {
  const router = useRouter();
  const routeReagentId = router.params.reagent_id || router.params.id;
  const reagentId = routeReagentId ? Number(routeReagentId) : 0;

  const [stockInfo, setStockInfo] = useState<StockInfo | null>(null);
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [remark, setRemark] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // 从详情页或试剂列表页带入 reagent_id 后，加载当前库存信息用于确认操作对象。
  const loadStockInfo = async () => {
    if (!reagentId) {
      setStockInfo(null);
      return;
    }

    setLoading(true);
    try {
      const data = await request<StockInfo>({ url: `/inventory/stock/${reagentId}` });
      setStockInfo(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "库存信息加载失败";
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStockInfo();
  }, [reagentId]);

  const handleSubmit = async () => {
    const parsedQuantity = Number(quantity);

    if (!reagentId) {
      Taro.showToast({ title: "请先选择试剂", icon: "none" });
      return;
    }

    if (!parsedQuantity || parsedQuantity <= 0) {
      Taro.showToast({ title: "入库数量必须大于0", icon: "none" });
      return;
    }

    setSubmitting(true);
    try {
      const result = await request<InventoryResponse>({
        url: "/inventory/in",
        method: "POST",
        data: {
          reagent_id: reagentId,
          quantity: parsedQuantity,
          reason: reason.trim() || undefined,
          remark: remark.trim() || undefined,
        },
      });

      Taro.showToast({
        title: `入库成功，当前库存：${result.after_quantity} ${result.unit || stockInfo?.unit || ""}`,
        icon: "success",
      });

      setQuantity("");
      await loadStockInfo();
    } catch (error) {
      const message = error instanceof Error ? error.message : "入库失败";
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setSubmitting(false);
    }
  };

  const goToReagentList = () => {
    Taro.navigateTo({ url: "/pages/reagent-list/index" });
  };

  return (
    <View className="page inventory-in-page">
      <Text className="page-title">试剂入库</Text>
      <Text className="page-subtitle">从试剂详情页带入试剂后，记录采购、补充库存等入库操作。</Text>

      {!reagentId ? (
        <View className="panel empty-panel">
          <Text className="panel-title">请先选择试剂</Text>
          <Text className="muted-text">入库操作需要先确定具体试剂，避免手动输入 ID 造成误操作。</Text>
          <Button className="primary-button choose-button" onClick={goToReagentList}>
            去选择试剂
          </Button>
        </View>
      ) : (
        <>
          <View className="panel stock-card">
            <Text className="panel-title">{stockInfo?.name_cn || (loading ? "加载中..." : "试剂信息")}</Text>
            <View className="stock-grid">
              <View className="stock-item">
                <Text className="stock-label">当前库存</Text>
                <Text className={stockInfo?.low_stock ? "stock-value warning" : "stock-value"}>
                  {stockInfo ? `${stockInfo.current_quantity} ${stockInfo.unit || ""}` : "--"}
                </Text>
              </View>
              <View className="stock-item">
                <Text className="stock-label">存放位置</Text>
                <Text className="stock-value">{formatValue(stockInfo?.location)}</Text>
              </View>
              <View className="stock-item">
                <Text className="stock-label">危险等级</Text>
                <Text className="stock-value">{formatValue(stockInfo?.hazard_level)}</Text>
              </View>
              <View className="stock-item">
                <Text className="stock-label">预警阈值</Text>
                <Text className="stock-value">
                  {stockInfo ? `${stockInfo.warning_threshold} ${stockInfo.unit || ""}` : "--"}
                </Text>
              </View>
            </View>
          </View>

          <View className="panel">
            <Text className="form-label">入库数量</Text>
            <Input
              className="form-input"
              type="digit"
              placeholder="请输入数量，必须大于0"
              value={quantity}
              onInput={(event) => setQuantity(event.detail.value)}
            />

            <Text className="form-label">原因</Text>
            <Input
              className="form-input"
              placeholder="例如：采购入库"
              value={reason}
              onInput={(event) => setReason(event.detail.value)}
            />

            <Text className="form-label">备注</Text>
            <Textarea
              className="form-input form-textarea"
              placeholder="可填写批号、供应商或其他说明"
              value={remark}
              onInput={(event) => setRemark(event.detail.value)}
            />
          </View>

          <Button className="primary-button" loading={submitting} onClick={handleSubmit}>
            提交入库
          </Button>
          <Button onClick={() => Taro.navigateBack()}>返回</Button>
        </>
      )}
    </View>
  );
}
