// 小程序只访问后端 HTTP API，不存放数据库连接串、SECRET_KEY 或管理员密码。
// 上线到真实微信小程序时，需要在微信公众平台把 Render 后端域名加入 request 合法域名。
// 开发者工具本地调试可临时勾选“不校验合法域名”。

//const LOCAL_API_BASE_URL = "http://127.0.0.1:8010";

// 部署后把这里改为 Render 后端地址，例如：
// const RENDER_API_BASE_URL = "https://your-render-backend.onrender.com";
//const RENDER_API_BASE_URL = "https://lab-reagent-backend.onrender.com";

//export const API_BASE_URL = RENDER_API_BASE_URL || LOCAL_API_BASE_URL;

//export const TOKEN_STORAGE_KEY = "access_token";
//export const USER_STORAGE_KEY = "current_user";

const LOCAL_API_BASE_URL = "http://127.0.0.1:8010";
const RENDER_API_BASE_URL = "https://lab-reagent-backend.onrender.com";

// 当前默认使用云端 Render 后端
export const API_BASE_URL = RENDER_API_BASE_URL;

// 如需本地开发调试，临时改为：
// export const API_BASE_URL = LOCAL_API_BASE_URL;

export const TOKEN_STORAGE_KEY = "access_token";
export const USER_STORAGE_KEY = "current_user";
