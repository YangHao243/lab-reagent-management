import Taro from "@tarojs/taro";
import { Button, Input, Text, View } from "@tarojs/components";
import { useEffect, useState } from "react";
import { request } from "../../utils/request";
import "./index.scss";

type Reagent = {
  id: number;
  label: string;
  value: number;
  name_cn: string;
  standard_name?: string;
  category?: string;
  current_quantity: number;
  unit: string;
  warning_threshold: number;
  location?: string;
  hazard_level?: string;
};

export default function ReagentList() {
  const [keyword, setKeyword] = useState("");
  const [reagents, setReagents] = useState<Reagent[]>([]);
  const [loading, setLoading] = useState(false);

  // 调用试剂选择器接口，默认返回 19 种预置试剂，搜索时按名称或 CAS 号模糊查询。
  const loadReagents = async (searchKeyword = keyword) => {
    setLoading(true);
    try {
      const data = await request<Reagent[]>({
        url: "/reagents/options",
        params: {
          keyword: searchKeyword.trim(),
          limit: 100,
        },
      });
      setReagents(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "试剂列表加载失败";
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReagents("");
  }, []);

  const openDetail = (id: number) => {
    Taro.navigateTo({ url: `/pages/reagent-detail/index?reagent_id=${id}` });
  };

  return (
    <View className="page reagent-list-page">
      <Text className="page-title">试剂列表</Text>
      <Text className="page-subtitle">按中文名、英文名或 CAS 号搜索试剂。</Text>

      <View className="search-panel">
        <Input
          className="search-input"
          placeholder="输入关键词搜索"
          value={keyword}
          confirmType="search"
          onInput={(event) => setKeyword(event.detail.value)}
          onConfirm={() => loadReagents()}
        />
        <Button className="search-button" size="mini" loading={loading} onClick={() => loadReagents()}>
          搜索
        </Button>
      </View>

      {reagents.length === 0 && !loading ? (
        <View className="panel">
          <Text className="muted-text">暂无试剂数据</Text>
        </View>
      ) : (
        reagents.map((item) => {
          const isLowStock = item.current_quantity <= item.warning_threshold;

          return (
            <View
              className={isLowStock ? "reagent-card low-stock" : "reagent-card"}
              key={item.id}
              onClick={() => openDetail(item.id)}
            >
              <View className="card-header">
                <Text className="reagent-name">{item.name_cn}</Text>
                {isLowStock && <Text className="low-stock-tag">低库存</Text>}
              </View>

              <Text className="reagent-line">分类：{item.category || "未分类"}</Text>
              <Text className="reagent-line">
                库存：{item.current_quantity} {item.unit}
              </Text>
              <Text className="reagent-line">
                预警阈值：{item.warning_threshold} {item.unit}
              </Text>
              <Text className="reagent-line">位置：{item.location || "未填写"}</Text>
              <Text className="reagent-line">危险等级：{item.hazard_level || "未填写"}</Text>
            </View>
          );
        })
      )}
    </View>
  );
}
