import Taro, { useDidShow, usePullDownRefresh, useReachBottom } from "@tarojs/taro";
import { Button, Input, Picker, Text, Textarea, View } from "@tarojs/components";
import { useState } from "react";
import { request } from "../../utils/request";
import { formatBeijingTime } from "../../utils/time";
import "./index.scss";

type OperationType = "in" | "out" | "adjust";
type OperationMode = OperationType;

type InventoryRecord = {
  id: number;
  year_display_id?: number;
  reagent_id: number;
  reagent_name?: string | null;
  operation_type: OperationType | string;
  quantity_change: number;
  before_quantity: number;
  after_quantity: number;
  operator_name?: string | null;
  reason?: string | null;
  remark?: string | null;
  created_at: string;
};

type ReagentOption = {
  id: number;
  label: string;
  value: number;
  name_cn: string;
  current_quantity: number;
  unit?: string | null;
  warning_threshold?: number;
  location?: string | null;
  category?: string | null;
};

type OperationResponse = {
  id: number;
  after_quantity: number;
  unit?: string | null;
  reagent_name?: string;
  low_stock?: boolean;
};

const PAGE_SIZE = 30;

const operationOptions: Array<{ label: string; value: "" | OperationType }> = [
  { label: "全部", value: "" },
  { label: "入库", value: "in" },
  { label: "出库", value: "out" },
  { label: "校正", value: "adjust" },
];

const operationCopy: Record<OperationMode, { title: string; action: string; tone: string; hint: string }> = {
  in: {
    title: "试剂入库",
    action: "入库",
    tone: "in",
    hint: "数量表示本次增加的库存数量。",
  },
  out: {
    title: "试剂出库",
    action: "出库",
    tone: "out",
    hint: "数量填写正数，后端会按出库扣减库存。",
  },
  adjust: {
    title: "库存校正",
    action: "校正",
    tone: "adjust",
    hint: "数量表示校正后的目标库存。",
  },
};

function getDefaultReason(mode: OperationMode) {
  if (mode === "in") return "领料入库";
  if (mode === "out") return "实验领用";
  return "库存校正";
}

function getReasonOptions(mode: OperationMode) {
  if (mode === "in") return ["领料入库", "其他原因"];
  if (mode === "out") return ["实验领用", "其他原因"];
  return ["库存校正", "其他原因"];
}

function getOperationMeta(type: string) {
  if (type === "in" || type === "入库") {
    return { label: "入库", className: "tag tag-green" };
  }
  if (type === "out" || type === "出库" || type === "领取") {
    return { label: "出库", className: "tag tag-red" };
  }
  return { label: "校正", className: "tag tag-blue" };
}

function getQuantityClass(value: number) {
  if (value > 0) return "quantity positive";
  if (value < 0) return "quantity negative";
  return "quantity";
}

function formatReagentLabel(item: ReagentOption) {
  return `${item.name_cn || item.label}｜库存 ${item.current_quantity} ${item.unit || ""}`;
}

type InventoryActionForm = {
  selectedReagent?: ReagentOption;
  quantity: string;
  operatorName: string;
  reason: string;
  remark: string;
};

type ValidatedInventoryAction = {
  reagentId: number;
  quantity: number;
  operatorName: string;
  reason: string;
  remark: string;
};

function isOtherReason(reason: string) {
  return reason === "其他原因" || reason === "其他";
}

function validateInventoryActionForm(
  form: InventoryActionForm,
  actionType: OperationMode,
): { ok: true; values: ValidatedInventoryAction } | { ok: false; message: string } {
  const _ = actionType;
  const quantityText = form.quantity.trim();
  const operatorName = form.operatorName.trim();
  const reason = form.reason.trim();
  const remark = form.remark.trim();

  if (!form.selectedReagent) {
    return { ok: false, message: "请选择试剂" };
  }

  if (!quantityText || !/^[1-9]\d*$/.test(quantityText)) {
    return { ok: false, message: "请输入大于 0 的整数数量" };
  }

  if (!operatorName) {
    return { ok: false, message: "请输入操作员姓名" };
  }

  if (!reason) {
    return { ok: false, message: "请选择原因" };
  }

  if (isOtherReason(reason) && !remark) {
    return { ok: false, message: "选择其他原因时，请填写备注说明" };
  }

  return {
    ok: true,
    values: {
      reagentId: form.selectedReagent.value || form.selectedReagent.id,
      quantity: Number(quantityText),
      operatorName,
      reason,
      remark,
    },
  };
}

export default function InventoryRecords() {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [operationType, setOperationType] = useState<"" | OperationType>("");
  const [records, setRecords] = useState<InventoryRecord[]>([]);
  const [reagentOptions, setReagentOptions] = useState<ReagentOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");

  const [operationOpen, setOperationOpen] = useState(false);
  const [operationMode, setOperationMode] = useState<OperationMode>("in");
  const [selectedReagentIndex, setSelectedReagentIndex] = useState(-1);
  const [quantity, setQuantity] = useState("");
  const [operatorName, setOperatorName] = useState("");
  const [reason, setReason] = useState("领料入库");
  const [remark, setRemark] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const selectedReagent = selectedReagentIndex >= 0 ? reagentOptions[selectedReagentIndex] : undefined;

  const loadRecords = async (options?: {
    reset?: boolean;
    nextYear?: number;
    nextOperationType?: "" | OperationType;
  }) => {
    const reset = options?.reset ?? false;
    const nextYear = options?.nextYear ?? year;
    const nextType = options?.nextOperationType ?? operationType;
    const skip = reset ? 0 : records.length;

    if (!reset && (!hasMore || loadingMore)) {
      return;
    }

    reset ? setLoading(true) : setLoadingMore(true);
    setError("");

    try {
      const data = await request<InventoryRecord[]>({
        url: "/inventory/records",
        params: {
          year: nextYear,
          operation_type: nextType || undefined,
          skip,
          limit: PAGE_SIZE,
        },
      });
      setRecords(reset ? data : [...records, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "库存流水加载失败";
      setError(message);
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
      setLoadingMore(false);
      Taro.stopPullDownRefresh();
    }
  };

  const loadReagentOptions = async () => {
    try {
      const data = await request<ReagentOption[]>({
        url: "/reagents/options",
        params: { limit: 500 },
      });
      setReagentOptions(data);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "试剂列表加载失败，请重试";
      Taro.showToast({ title: message, icon: "none" });
    }
  };

  useDidShow(() => {
    loadRecords({ reset: true });
    loadReagentOptions();
  });

  usePullDownRefresh(() => {
    loadRecords({ reset: true });
    loadReagentOptions();
  });

  useReachBottom(() => {
    loadRecords();
  });

  const changeYear = (offset: number) => {
    const nextYear = year + offset;
    setYear(nextYear);
    loadRecords({ reset: true, nextYear });
  };

  const changeOperationType = (nextType: "" | OperationType) => {
    setOperationType(nextType);
    loadRecords({ reset: true, nextOperationType: nextType });
  };

  const resetOperationForm = (mode = operationMode) => {
    setSelectedReagentIndex(-1);
    setQuantity("");
    setOperatorName("");
    setReason(getDefaultReason(mode));
    setRemark("");
  };

  const openOperation = (mode: OperationMode) => {
    setOperationMode(mode);
    resetOperationForm(mode);
    setOperationOpen(true);
    if (reagentOptions.length === 0) {
      loadReagentOptions();
    }
  };

  const closeOperation = () => {
    if (submitting) return;
    setOperationOpen(false);
    resetOperationForm();
  };

  const submitOperation = async () => {
    const validated = validateInventoryActionForm(
      {
        selectedReagent,
        quantity,
        operatorName,
        reason,
        remark,
      },
      operationMode,
    );
    if (!validated.ok) {
      Taro.showToast({ title: validated.message, icon: "none" });
      return;
    }

    const endpoint =
      operationMode === "in"
        ? "/inventory/in"
        : operationMode === "out"
          ? "/inventory/out"
          : "/inventory/adjust";

    setSubmitting(true);
    try {
      const result = await request<OperationResponse>({
        url: endpoint,
        method: "POST",
        data: {
          reagent_id: validated.values.reagentId,
          quantity: validated.values.quantity,
          operator_name: validated.values.operatorName,
          reason: validated.values.reason,
          remark: validated.values.remark || undefined,
        },
      });

      Taro.showToast({
        title: `${operationCopy[operationMode].action}成功`,
        icon: "success",
      });
      setOperationOpen(false);
      resetOperationForm();
      await Promise.all([loadRecords({ reset: true }), loadReagentOptions()]);

      if (result.low_stock) {
        setTimeout(() => {
          Taro.showModal({
            title: "低库存提醒",
            content: `${result.reagent_name || selectedReagent?.name_cn || "当前试剂"} 当前库存 ${result.after_quantity} ${
              result.unit || selectedReagent?.unit || ""
            }，请关注补充。`,
            showCancel: false,
          });
        }, 700);
      }
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "操作失败";
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setSubmitting(false);
    }
  };

  const reasonOptions = getReasonOptions(operationMode);

  return (
    <View className="page inventory-records-page">
      <View className="hero-card">
        <Text className="hero-icon">⇄</Text>
        <View className="hero-copy">
          <Text className="page-title hero-title">库存流水</Text>
          <Text className="page-subtitle hero-subtitle">
            移动端支持基础入库、出库与库存校正，适合日常快速记录。
          </Text>
        </View>
      </View>

      <View className="toolbar panel">
        <Text className="panel-caption">年份筛选</Text>
        <View className="year-row">
          <Button className="year-button" size="mini" onClick={() => changeYear(-1)}>
            上一年
          </Button>
          <Text className="year-text">{year}</Text>
          <Button className="year-button" size="mini" onClick={() => changeYear(1)}>
            下一年
          </Button>
        </View>

        <Text className="panel-caption">操作筛选</Text>
        <View className="operation-row">
          {operationOptions.map((item) => (
            <Text
              className={operationType === item.value ? "filter-chip active" : "filter-chip"}
              key={item.value || "all"}
              onClick={() => changeOperationType(item.value)}
            >
              {item.label}
            </Text>
          ))}
        </View>
      </View>

      <View className="quick-panel panel">
        <Text className="panel-caption">快捷操作</Text>
        <View className="quick-actions">
          <Button className="quick-button in" onClick={() => openOperation("in")}>
            入库
          </Button>
          <Button className="quick-button out" onClick={() => openOperation("out")}>
            出库
          </Button>
          <Button className="quick-button adjust" onClick={() => openOperation("adjust")}>
            校正
          </Button>
        </View>
      </View>

      {error ? (
        <View className="panel state-card">
          <Text className="state-title">加载失败</Text>
          <Text className="muted-text">{error}</Text>
          <Button className="state-action" loading={loading} onClick={() => loadRecords({ reset: true })}>
            重试
          </Button>
        </View>
      ) : null}

      {records.length === 0 && !loading ? (
        <View className="panel state-card">
          <Text className="state-title">暂无流水</Text>
          <Text className="muted-text">当前筛选条件下没有库存流水记录。</Text>
        </View>
      ) : (
        records.map((record) => {
          const meta = getOperationMeta(record.operation_type);
          return (
            <View className="record-card" key={record.id}>
              <View className="record-header">
                <View className="record-title-block">
                  <Text className="record-name">
                    {record.reagent_name || `#${record.reagent_id}`}
                  </Text>
                  <Text className="record-time">{formatBeijingTime(record.created_at)}</Text>
                </View>
                <Text className={meta.className}>{meta.label}</Text>
              </View>

              <View className="quantity-row">
                <View className="quantity-item">
                  <Text className="quantity-label">变化数量</Text>
                  <Text className={getQuantityClass(record.quantity_change)}>
                    {record.quantity_change}
                  </Text>
                </View>
                <View className="quantity-item">
                  <Text className="quantity-label">操作前</Text>
                  <Text className="quantity">{record.before_quantity}</Text>
                </View>
                <View className="quantity-item">
                  <Text className="quantity-label">操作后</Text>
                  <Text className="quantity">{record.after_quantity}</Text>
                </View>
              </View>

              <View className="meta-row">
                <Text className="meta-label">操作员</Text>
                <Text className="meta-value">{record.operator_name || "-"}</Text>
              </View>
              <View className="meta-row">
                <Text className="meta-label">原因</Text>
                <Text className="meta-value">{record.reason || "-"}</Text>
              </View>
              <View className="meta-row remark">
                <Text className="meta-label">备注</Text>
                <Text className="meta-value">{record.remark || "-"}</Text>
              </View>
            </View>
          );
        })
      )}

      {loadingMore ? <Text className="list-footer">加载更多...</Text> : null}
      {!hasMore && records.length > 0 ? <Text className="list-footer">已加载全部</Text> : null}

      {operationOpen ? (
        <View className="modal-mask">
          <View className="operation-modal">
            <View className={`modal-header ${operationCopy[operationMode].tone}`}>
              <Text className="modal-title">{operationCopy[operationMode].title}</Text>
              <Text className="modal-hint">{operationCopy[operationMode].hint}</Text>
            </View>

            <Text className="form-label">
              <Text className="required-star">*</Text>试剂选择
            </Text>
            <Picker
              mode="selector"
              range={reagentOptions.map(formatReagentLabel)}
              value={selectedReagentIndex < 0 ? 0 : selectedReagentIndex}
              onChange={(event) => setSelectedReagentIndex(Number(event.detail.value))}
            >
              <View className="picker-box">
                <Text className={selectedReagent ? "picker-text" : "picker-placeholder"}>
                  {selectedReagent ? formatReagentLabel(selectedReagent) : "请选择试剂"}
                </Text>
              </View>
            </Picker>
            {selectedReagent ? (
              <Text className="selected-stock">
                当前库存：{selectedReagent.current_quantity} {selectedReagent.unit || ""} ·{" "}
                {selectedReagent.location || "未填写位置"}
              </Text>
            ) : null}

            <Text className="form-label">
              <Text className="required-star">*</Text>
              {operationMode === "adjust" ? "目标库存" : "数量"}
            </Text>
            <Input
              className="form-input"
              type="number"
              placeholder="请输入大于 0 的整数"
              value={quantity}
              onInput={(event) => setQuantity(event.detail.value)}
            />

            <Text className="form-label">
              <Text className="required-star">*</Text>操作员
            </Text>
            <Input
              className="form-input"
              placeholder="请输入实际操作人姓名"
              value={operatorName}
              onInput={(event) => setOperatorName(event.detail.value)}
            />

            <Text className="form-label">
              <Text className="required-star">*</Text>原因
            </Text>
            <View className="reason-row">
              {reasonOptions.map((item) => (
                <Text
                  key={item}
                  className={reason === item ? "reason-chip active" : "reason-chip"}
                  onClick={() => setReason(item)}
                >
                  {item}
                </Text>
              ))}
            </View>

            <Text className="form-label">备注（其他原因必填）</Text>
            <Textarea
              className="form-input form-textarea"
              placeholder="可填写批次、用途或说明；选择其他原因时必填"
              value={remark}
              onInput={(event) => setRemark(event.detail.value)}
            />

            <View className="modal-actions">
              <Button className="cancel-button" onClick={closeOperation}>
                取消
              </Button>
              <Button className={`submit-button ${operationCopy[operationMode].tone}`} loading={submitting} onClick={submitOperation}>
                提交
              </Button>
            </View>
          </View>
        </View>
      ) : null}
    </View>
  );
}
