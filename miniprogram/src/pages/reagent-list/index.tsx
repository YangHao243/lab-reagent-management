import Taro, { useDidShow, usePullDownRefresh, useReachBottom } from "@tarojs/taro";
import { Button, Input, ScrollView, Text, View } from "@tarojs/components";
import { useState } from "react";
import { request } from "../../utils/request";
import "./index.scss";

type Reagent = {
  id: number;
  name_cn: string;
  name_en?: string | null;
  cas_no?: string | null;
  category?: string | null;
  purity_grade?: string | null;
  current_quantity: number;
  unit?: string | null;
  warning_threshold: number;
  location?: string | null;
  hazard_level?: string | null;
};

const PAGE_SIZE = 20;

export default function ReagentList() {
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [reagents, setReagents] = useState<Reagent[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");

  const loadCategories = async () => {
    try {
      const data = await request<string[]>({ url: "/reagents/categories/list" });
      setCategories(data);
    } catch {
      // 分类失败不阻塞主列表。
    }
  };

  const loadReagents = async (options?: { reset?: boolean; nextCategory?: string; nextKeyword?: string }) => {
    const reset = options?.reset ?? false;
    const nextCategory = options?.nextCategory ?? category;
    const nextKeyword = options?.nextKeyword ?? keyword;
    const skip = reset ? 0 : reagents.length;

    if (!reset && (!hasMore || loadingMore)) {
      return;
    }

    reset ? setLoading(true) : setLoadingMore(true);
    setError("");

    try {
      const data = await request<Reagent[]>({
        url: "/reagents/",
        params: {
          keyword: nextKeyword.trim(),
          category: nextCategory,
          skip,
          limit: PAGE_SIZE,
        },
      });
      setReagents(reset ? data : [...reagents, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "试剂列表加载失败";
      setError(message);
      Taro.showToast({ title: message, icon: "none" });
    } finally {
      setLoading(false);
      setLoadingMore(false);
      Taro.stopPullDownRefresh();
    }
  };

  useDidShow(() => {
    loadCategories();
    loadReagents({ reset: true });
  });

  usePullDownRefresh(() => {
    loadCategories();
    loadReagents({ reset: true });
  });

  useReachBottom(() => {
    loadReagents();
  });

  const openDetail = (id: number) => {
    Taro.navigateTo({ url: `/pages/reagent-detail/index?reagent_id=${id}` });
  };

  const submitSearch = () => {
    loadReagents({ reset: true });
  };

  const changeCategory = (nextCategory: string) => {
    setCategory(nextCategory);
    loadReagents({ reset: true, nextCategory });
  };

  return (
    <View className="page reagent-list-page">
      <Text className="page-title">试剂库存</Text>
      <Text className="page-subtitle">按名称、CAS 号或分类快速查找试剂库存状态。</Text>

      <View className="search-panel">
        <Input
          className="search-input"
          placeholder="中文名 / 英文名 / CAS 号"
          value={keyword}
          confirmType="search"
          onInput={(event) => setKeyword(event.detail.value)}
          onConfirm={submitSearch}
        />
        <Button className="search-button" size="mini" loading={loading} onClick={submitSearch}>
          搜索
        </Button>
      </View>

      <ScrollView className="category-scroll" scrollX enhanced showScrollbar={false}>
        <View className="category-row">
          <Text
            className={category === "" ? "filter-chip active" : "filter-chip"}
            onClick={() => changeCategory("")}
          >
            全部
          </Text>
          {categories.map((item) => (
            <Text
              className={category === item ? "filter-chip active" : "filter-chip"}
              key={item}
              onClick={() => changeCategory(item)}
            >
              {item}
            </Text>
          ))}
        </View>
      </ScrollView>

      {error ? (
        <View className="panel state-card">
          <Text className="state-title">加载失败</Text>
          <Text className="muted-text">{error}</Text>
          <Button className="state-action" onClick={() => loadReagents({ reset: true })}>
            重试
          </Button>
        </View>
      ) : null}

      {reagents.length === 0 && !loading ? (
        <View className="panel state-card">
          <Text className="state-title">暂无试剂</Text>
          <Text className="muted-text">可以尝试换一个关键词或分类。</Text>
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
                <View className="name-block">
                  <Text className="reagent-name">{item.name_cn}</Text>
                  <Text className="reagent-subtitle">{item.name_en || item.cas_no || "暂无英文名 / CAS"}</Text>
                </View>
                {isLowStock ? <Text className="tag tag-red">低库存</Text> : <Text className="tag tag-green">正常</Text>}
              </View>

              <View className="info-grid">
                <View className="info-item">
                  <Text className="info-label">分类</Text>
                  <Text className="info-value">{item.category || "未分类"}</Text>
                </View>
                <View className="info-item">
                  <Text className="info-label">纯度</Text>
                  <Text className="info-value">{item.purity_grade || "-"}</Text>
                </View>
                <View className="info-item">
                  <Text className="info-label">当前库存</Text>
                  <Text className={isLowStock ? "info-value danger" : "info-value"}>
                    {item.current_quantity} {item.unit || ""}
                  </Text>
                </View>
                <View className="info-item">
                  <Text className="info-label">预警阈值</Text>
                  <Text className="info-value">
                    {item.warning_threshold} {item.unit || ""}
                  </Text>
                </View>
              </View>

              <Text className="reagent-line">位置：{item.location || "未填写"} · 危险等级：{item.hazard_level || "未填写"}</Text>
            </View>
          );
        })
      )}

      {loadingMore ? <Text className="list-footer">加载更多...</Text> : null}
      {!hasMore && reagents.length > 0 ? <Text className="list-footer">已加载全部</Text> : null}
    </View>
  );
}
