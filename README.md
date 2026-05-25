# Lab Reagent Management System

实验室化学试剂仓库管理系统 —— 面向实验室试剂出入库、库存余量、报警提醒、报表统计、Excel/CSV 导入导出、腾讯文档同步和后台管理的全栈 Web 应用。

## 1. 项目简介

本项目用于解决实验室化学试剂人工登记不便、库存统计不及时、出入库记录分散、腾讯文档与系统数据难以同步等问题。

**适用场景**：高校/企业化学实验室、生物实验室、检测中心等需要管理试剂库存的环境。

**技术定位**：全栈单体应用。后端使用 Python FastAPI + SQLAlchemy，前端管理后台使用 React + TypeScript + Ant Design，微信小程序端提供移动端查询入口，数据库支持本地 SQLite（开发）和 PostgreSQL/Supabase（生产）。

## 2. 核心功能

### 2.1 试剂基础信息管理

- 试剂中文名、英文名、CAS 号、分类、规格、单位
- 标准名称、纯度等级、别名（Excel 主数据迁移支持）
- 当前库存数量、预警阈值
- 存放位置、供应商、危险等级、有效期、备注
- 预置试剂排序 (`display_order`)

### 2.2 入库 / 出库 / 领取流水

- 入库（in）、出库/领取（out）、库存校正（adjust）三种操作类型
- 操作人、操作日期、数量变化（正负数自动归一化）
- 库存自动重算：每次流水变更后按时间顺序重算 `before_quantity` / `after_quantity`
- 去重逻辑：基于业务唯一键（试剂 + 操作类型 + 操作员 + 数量 + 时间）和 source_hash 双重去重

### 2.3 库存报警

- 低库存阈值判断（`current_quantity <= warning_threshold`）
- 有效期临近提醒（`EXPIRY_WARNING_DAYS` 可配置）
- 管理后台"报警管理"页面展示

### 2.4 报表统计

- **总览统计**：试剂总数、低库存数量、今日出入库次数
- **出入库趋势图**：日统计 / 月统计 / 年统计，ECharts 折线图展示入库/出库次数和数量
- **消耗 Top N**：按消耗量排序的试剂排行，包含出库次数、消耗量、入库次数、入库数量、校正量
- **分类库存汇总**：按试剂分类统计数量、低库存数、总库存量
- 时间筛选：日模式（某月每日）、月模式（某年每月）、年模式（近 5 年每年）

### 2.5 Excel / CSV 导入导出

- **Excel 导入**：支持历史库存宽表 `.xlsx/.xls` 格式，自动解析横向月度矩阵（每种试剂 3 列：操作/数量/操作人）
- **CSV 导入**：支持试剂主数据 `.csv` 格式，CAS 号优先去重、中文名兜底
- **Excel 导出**：按年份生成库存流水模板 `.xlsx` 文件
- 日期解析：兼容多种 Excel 日期格式，按北京时间（Asia/Shanghai）统一处理

### 2.6 腾讯文档同步

对接腾讯文档 OpenAPI，实现本地数据库与在线表格的双向同步。

**已实现功能**：

- **Direct Token 模式**：使用 `client_id` + `access_token` + `open_id` 调用腾讯文档 API
- **Sheet 自动探测**：调用 spreadsheet V3 API 获取文件中所有子表列表
- **sheetID 自动解析**：根据用户选择的年份和月份，按 sheet 标题（如 `2026.5`）自动匹配目标 sheetID
- **单月导入**：从腾讯文档对应月份 sheet 读取出入库流水并写入本地数据库
- **全年导入**：依次处理 1—12 月所有 sheet
- **单月同步**：将本地数据库出入库记录增量写入腾讯文档对应月份 sheet
- **全年同步**：逐月处理 1—12 月，每月独立写入对应 sheet
- **非破坏性增量追加**：读取腾讯文档已有单元格内容，在原有基础上追加数据库中的新记录，只写变更的 1×3 小范围（如 `H28:J28`），不会整块覆盖或清空原表
- **Write-Cell 测试**：快速连通性测试，默认写入 `000001!A1:A1` 一个单元格
- **导入预检**：预览腾讯文档矩阵解析结果而不写入数据库
- **导出预览**：预览将要写入的 patch 而不会实际调用腾讯文档 API
- **后台 Job 模式**：正式导入/同步通过后台任务执行，前端轮询进度，避免长时间阻塞
- **Token 过期提醒**：管理员可手动维护 Direct Token 过期时间，前端显示有效/即将过期/已过期状态

**配置说明**详见 [docs/tencent-docs-sync.md](docs/tencent-docs-sync.md)。

### 2.7 管理后台

- React + TypeScript + Ant Design 5 管理后台
- 用户身份认证（JWT），角色权限控制（viewer / manager / admin / superadmin）
- **试剂列表**：分页查询、搜索、筛选、增删改查
- **入库/出库**：登记出入库记录，自动重算库存
- **库存流水**：查看全部出入库流水记录，支持批量删除
- **报表统计**：ECharts 图表 + Top N 表格 + 分类汇总
- **腾讯文档同步**：完整的同步配置、调试工具和操作面板
- **用户管理**：管理员创建/禁用用户，角色分配
- **报警管理**：低库存和有效期提醒列表

### 2.8 微信小程序端

`miniprogram/` 目录包含微信小程序前端代码（Taro + React），提供移动端试剂查询、库存流水查看、报警列表查看等功能。小程序通过 HTTP API 与后端通信。

当前状态：基础页面已实现（试剂列表、试剂详情、库存流水、报警、个人中心），可根据需要继续扩展。

## 3. 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| Python 3.10+ | 运行时 |
| FastAPI | Web 框架，自动生成 OpenAPI 文档 |
| SQLAlchemy 2.0 | ORM 数据库访问 |
| Alembic | 数据库迁移管理 |
| Pydantic v2 | 请求/响应模型校验 |
| Pydantic Settings | 环境变量与配置管理 |
| python-jose | JWT 令牌生成与验证 |
| passlib + bcrypt | 密码哈希 |
| APScheduler | 定时任务调度 |
| pandas + openpyxl | Excel 文件读写 |
| requests | HTTP 客户端（腾讯文档 API） |
| Uvicorn | ASGI 服务器 |

**数据库**：本地开发使用 SQLite，生产环境支持 PostgreSQL（含 Supabase）。

### 前端管理后台

| 技术 | 用途 |
|------|------|
| React 18 | UI 框架 |
| TypeScript 5 | 类型安全 |
| Vite 6 | 构建工具 |
| pnpm | 包管理器 |
| Ant Design 5 | UI 组件库 |
| ECharts 5 | 图表可视化 |
| Axios | HTTP 客户端 |
| React Router 6 | 前端路由 |

### 微信小程序端

| 技术 | 用途 |
|------|------|
| Taro | 跨平台小程序框架 |
| React | UI 框架 |
| TypeScript | 类型安全 |

### 部署与运维

| 服务 | 用途 |
|------|------|
| Render | 后端 Python 服务托管 |
| Cloudflare Pages | 前端静态网站托管 |
| Supabase | 生产环境 PostgreSQL 数据库 |
| 腾讯文档 OpenAPI | 在线表格读写 |

## 4. 项目目录结构

```text
lab_reagent/
├── backend/                          # 后端 FastAPI 服务
│   ├── main.py                       # 应用入口，路由挂载，CORS，生命周期
│   ├── config.py                     # 配置类（环境变量读取，默认值）
│   ├── database.py                   # 数据库引擎、会话工厂、init_db()
│   ├── models.py                     # ORM 模型定义（共 9 张表）
│   ├── dependencies.py               # FastAPI 依赖注入（认证、权限）
│   ├── auth.py                       # 用户认证与 JWT 逻辑
│   ├── users.py                      # 用户管理 API
│   ├── reagents.py                   # 试剂管理 API
│   ├── inventory.py                  # 库存流水 API
│   ├── alerts.py                     # 报警管理 API
│   ├── reports.py                    # 报表统计 API
│   ├── sync_api.py                   # 统一同步 API（Mock/Excel/CSV）
│   ├── tencent_docs.py               # 旧版腾讯文档接口（兼容保留）
│   ├── tencent_docs_api.py           # 新版腾讯文档真实同步 API
│   ├── scheduler.py                  # 定时任务调度
│   ├── notifications.py              # 通知服务
│   ├── schemas.py                    # Pydantic 请求/响应模型
│   ├── seed_data.py                  # 种子数据生成
│   ├── seed_superadmin.py            # 超级管理员初始化
│   ├── requirements.txt              # Python 依赖
│   ├── alembic/                      # 数据库迁移
│   │   └── versions/                 # 迁移版本文件
│   ├── services/                     # 业务服务层
│   │   ├── excel_inventory_sync.py   # Excel 导入导出核心逻辑
│   │   ├── csv_reagent_sync.py       # CSV 试剂导入
│   │   ├── sync_core.py             # 统一导入/导出服务、库存计算
│   │   ├── sync_providers.py         # 同步 Provider（Excel/Mock/腾讯文档）
│   │   ├── tencent_docs_matrix.py    # 腾讯文档矩阵模板解析与生成
│   │   ├── tencent_docs_jobs.py      # 腾讯文档后台 Job 执行器
│   │   ├── tencent_docs_schema.py    # 腾讯文档相关表迁移
│   │   └── token_expiry.py           # Token 过期时间管理
│   ├── utils/                        # 工具模块
│   │   └── timezone.py               # 北京时间工具函数
│   └── tests/                        # 后端测试
│       ├── test_core_api.py
│       └── test_excel_inventory_date_parse.py
│
├── admin-web/                        # React 管理后台
│   ├── src/
│   │   ├── main.tsx                  # 应用入口
│   │   ├── App.tsx                   # 路由配置
│   │   ├── api/client.ts             # Axios 实例封装
│   │   ├── auth/                     # 认证模块
│   │   │   ├── AuthContext.tsx        # 认证上下文
│   │   │   └── storage.ts            # Token 本地存储
│   │   ├── pages/                    # 页面组件
│   │   │   ├── Login.tsx             # 登录页
│   │   │   ├── Dashboard.tsx         # 总览仪表盘
│   │   │   ├── ReagentList.tsx       # 试剂列表管理
│   │   │   ├── InventoryRecords.tsx  # 库存流水记录
│   │   │   ├── Alerts.tsx            # 报警管理
│   │   │   ├── Reports.tsx           # 报表统计
│   │   │   ├── TencentDocsSync.tsx   # 腾讯文档同步
│   │   │   └── Users.tsx             # 用户管理
│   │   └── utils/time.ts             # 时间格式化工具
│   ├── package.json                  # 前端依赖
│   ├── tsconfig.json                 # TypeScript 配置
│   └── vite.config.ts                # Vite 构建配置
│
├── miniprogram/                      # 微信小程序端（Taro + React）
│   ├── src/
│   │   ├── app.config.ts             # 小程序全局配置
│   │   ├── app.tsx                   # 小程序入口
│   │   ├── config.ts                 # API 地址与存储 key
│   │   ├── pages/                    # 页面
│   │   │   ├── index/                # 首页
│   │   │   ├── reagent-list/         # 试剂列表
│   │   │   ├── reagent-detail/       # 试剂详情
│   │   │   ├── inventory-records/    # 库存流水
│   │   │   ├── inventory-in/         # 入库登记
│   │   │   ├── inventory-out/        # 出库登记
│   │   │   ├── alerts/               # 报警列表
│   │   │   ├── reports/              # 报表
│   │   │   └── profile/              # 个人中心
│   │   └── utils/time.ts             # 时间格式化
│   └── project.config.json           # 小程序项目配置
│
├── docs/                             # 项目文档
│   └── tencent-docs-sync.md          # 腾讯文档同步配置说明
│
├── scripts/                          # 运维脚本
│   ├── local_smoke_test.py           # 本地冒烟测试
│   └── test_excel_reagent_workflow.py # Excel 试剂工作流测试
│
├── .gitignore                        # Git 忽略规则
├── render.yaml                       # Render 部署蓝图
└── README.md                         # 本文件
```

## 5. 数据库模型概览

| 表名 | 说明 |
|------|------|
| `users` | 系统用户（用户名、密码哈希、角色、邮箱） |
| `reagents` | 试剂基础信息与当前库存（名称、CAS 号、规格、单位、数量、阈值等） |
| `inventory_records` | 库存流水（出入库记录、操作类型、数量变化、前后库存） |
| `alert_events` | 报警事件（低库存提醒、有效期临近提醒） |
| `sync_logs` | 同步日志（同步来源、类型、状态、消息、详情 JSON） |
| `tencent_docs_tokens` | 腾讯文档 OAuth Token 存储 |
| `tencent_docs_sync_jobs` | 腾讯文档后台同步任务（Job 模式） |
| `system_settings` | 系统级键值配置（如 token 过期时间） |
| `audit_logs` | 操作审计日志 |

## 6. 快速开始

### 6.1 环境要求

- Python >= 3.10
- Node.js >= 18
- pnpm（前端包管理）
- Git

### 6.2 后端启动（本地开发）

```bash
cd backend

# 1. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少保留 ENVIRONMENT=development

# 4. 初始化数据库并启动
python seed_superadmin.py   # 创建默认超级管理员（可选）
uvicorn main:app --reload --port 8010
```

后端启动后访问：
- API 文档：<http://127.0.0.1:8010/docs>
- 健康检查：<http://127.0.0.1:8010/health>

默认超级管理员账号（本地开发，仅首次使用）：
- 用户名：`superadmin`
- 密码：`Admin@123456`
- 生产环境务必通过 `.env` 中 `DEFAULT_SUPERADMIN_USERNAME` / `DEFAULT_SUPERADMIN_PASSWORD` 覆盖

### 6.3 前端管理后台启动（本地开发）

```bash
cd admin-web

# 1. 安装依赖
pnpm install

# 2. 复制环境变量示例
cp .env.example .env

# 3. 启动开发服务器
pnpm dev
```

前端默认运行在 <http://127.0.0.1:5173>，会自动代理 API 请求到后端。

### 6.4 微信小程序端启动（本地开发）

```bash
cd miniprogram

# 1. 安装依赖
pnpm install

# 2. 使用微信开发者工具打开 miniprogram 目录
# 3. 在 config.ts 中配置后端 API 地址
# 4. 开发者工具中勾选"不校验合法域名"（仅调试用）
```

## 7. 环境变量参考

后端核心环境变量（详见 `backend/.env.example`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENVIRONMENT` | 运行环境：`development` / `production` | `development` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./lab_reagent.db` |
| `SECRET_KEY` | JWT 签名密钥 | 默认值（生产必须更换） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT 过期时间（分钟） | `480` |
| `CORS_ORIGINS` | 允许的前端域名，逗号分隔 | `*` |
| `TENCENT_DOCS_MODE` | 腾讯文档模式：`real` / `mock` / `local` | `local` |
| `TENCENT_DOCS_ACCESS_TOKEN` | 腾讯文档 Direct Token | 空 |

**注意**：生产环境必须通过环境变量覆盖 `SECRET_KEY`、数据库连接串和腾讯文档配置，不要将 `.env` 提交到 Git。

## 8. 部署

### 8.1 Render（后端）

项目根目录包含 `render.yaml` 蓝图文件，可直接在 Render Dashboard 中通过 Blueprint 一键部署：

```bash
# 或手动创建 Web Service：
# Runtime: Python 3
# Build Command: pip install -r requirements.txt
# Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
# Root Directory: backend
```

### 8.2 Cloudflare Pages（前端管理后台）

```bash
cd admin-web
pnpm build    # 输出到 dist/ 目录
```

将 `dist/` 目录部署到 Cloudflare Pages，设置环境变量指向后端 Render 地址。`admin-web/public/_redirects` 已配置 SPA 路由回退规则。

### 8.3 Supabase（数据库）

生产环境使用 Supabase PostgreSQL，将连接串配置为：

```env
DATABASE_URL=postgresql+psycopg2://postgres.xxxxx:password@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
```

首次部署自动运行 `init_db()` 创建所有表。Alembic 迁移文件位于 `backend/alembic/versions/`。

## 9. API 接口概览

| 模块 | 前缀 | 说明 |
|------|------|------|
| Auth | `/auth` | 登录、令牌刷新 |
| Users | `/users` | 用户 CRUD |
| Reagents | `/reagents` | 试剂管理 |
| Inventory | `/inventory` | 库存流水 |
| Alerts | `/alerts` | 报警管理 |
| Reports | `/reports` | 报表统计、消耗 Top N |
| Sync | `/api/sync` | 统一同步（Mock/Excel/CSV） |
| Tencent Docs | `/api/tencent-docs` | 腾讯文档真实同步 |
| Tencent Docs (旧) | `/tencent-docs` | 旧版兼容接口 |
| Health | `/health` | 健康检查 |

## 10. 角色与权限

| 角色 | 权限 |
|------|------|
| `viewer` | 只读查看试剂、库存、报表、同步状态和日志 |
| `manager` | 查看 + 出入库操作 + 报警处理 |
| `admin` | 全部管理功能（含腾讯文档同步、用户管理） |
| `superadmin` | 全部权限 + 系统初始化配置 |

## 11. 腾讯文档同步快速参考

| 操作 | 说明 |
|------|------|
| 探测 Sheet 列表 | 获取腾讯文档中所有子表信息 |
| 导入预检 | 预览腾讯文档数据解析结果，不写入数据库 |
| 导出预览 | 预览将要同步的增量 patch，不调用腾讯 API |
| Write-Cell 测试 | 测试写入 API 连通性（仅写一个单元格） |
| 从腾讯文档导入 | 选择单月/全年，将腾讯文档数据导入本地数据库 |
| 同步到腾讯文档 | 选择单月/全年，将本地数据增量写入腾讯文档 |

详见 [docs/tencent-docs-sync.md](docs/tencent-docs-sync.md)。

## 12. 许可证

本项目仅供学习和内部使用。如需商用或二次分发，请联系项目维护者。

## 13. 联系方式

维护者邮箱：neuyh2023@163.com
