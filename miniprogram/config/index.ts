import { defineConfig, type UserConfigExport } from "@tarojs/cli";
import devConfig from "./dev";
import prodConfig from "./prod";

export default defineConfig(async (merge) => {
  const baseConfig: UserConfigExport = {
    projectName: "lab-reagent-miniprogram",
    date: "2026-05-18",
    designWidth: 750,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      828: 1.81 / 2,
    },
    sourceRoot: "src",
    outputRoot: "dist",
    framework: "react",
    compiler: "webpack5",
    plugins: [],
    defineConstants: {},
    copy: {
      patterns: [],
      options: {},
    },
    mini: {
      postcss: {
        pxtransform: {
          enable: true,
          config: {},
        },
        cssModules: {
          enable: false,
          config: {
            namingPattern: "module",
            generateScopedName: "[name]__[local]___[hash:base64:5]",
          },
        },
      },
    },
  };

  // 根据运行环境合并开发或生产配置，保持基础配置足够简单。
  return merge({}, baseConfig, process.env.NODE_ENV === "development" ? devConfig : prodConfig);
});
