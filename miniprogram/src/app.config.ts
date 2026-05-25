export default defineAppConfig({
  pages: [
    "pages/index/index",
    "pages/reagent-list/index",
    "pages/reagent-detail/index",
    "pages/inventory-records/index",
    "pages/inventory-in/index",
    "pages/inventory-out/index",
    "pages/alerts/index",
    "pages/reports/index",
    "pages/profile/index",
  ],
  window: {
    backgroundTextStyle: "light",
    navigationBarBackgroundColor: "#155e75",
    navigationBarTitleText: "试剂仓库",
    navigationBarTextStyle: "white",
  },
  tabBar: {
    color: "#78909c",
    selectedColor: "#1677ff",
    backgroundColor: "#ffffff",
    borderStyle: "white",
    list: [
      { pagePath: "pages/index/index", text: "仪表盘" },
      { pagePath: "pages/reagent-list/index", text: "试剂库存" },
      { pagePath: "pages/inventory-records/index", text: "库存流水" },
      { pagePath: "pages/alerts/index", text: "报警事件" },
      { pagePath: "pages/reports/index", text: "报表统计" },
    ],
  },
});
