export default defineAppConfig({
  pages: [
    "pages/index/index",
    "pages/reagent-list/index",
    "pages/reagent-detail/index",
    "pages/inventory-in/index",
    "pages/inventory-out/index",
    "pages/alerts/index",
    "pages/profile/index",
  ],
  window: {
    backgroundTextStyle: "light",
    navigationBarBackgroundColor: "#0f766e",
    navigationBarTitleText: "试剂仓库",
    navigationBarTextStyle: "white",
  },
});
