# 腾讯文档同步配置说明

当前系统支持两种腾讯文档真实同步配置方式。生产环境请把变量配置在后端运行环境中，不要提交 `.env`。

## 模式 A：OAuth 模式

适用于已经拿到 OAuth 应用密钥和回调地址的场景。后端会通过授权流程获取并保存 token。

```env
TENCENT_DOCS_MODE=real
TENCENT_DOCS_CLIENT_ID=your-client-id
TENCENT_DOCS_CLIENT_SECRET=your-client-secret
TENCENT_DOCS_REDIRECT_URI=https://your-backend.example.com/callback
TENCENT_DOCS_FILE_ID=your-doc-file-id
TENCENT_DOCS_DEFAULT_YEAR=2026
```

`client_secret` 只用于 OAuth 换取 token，不会返回给前端。

## 模式 B：Direct Token 模式

适用于腾讯文档开放生态后台只提供 `client_id`、`access_token`、`open_id` 的场景。当前项目优先兼容该模式。

```env
TENCENT_DOCS_MODE=real
TENCENT_DOCS_CLIENT_ID=your-client-id
TENCENT_DOCS_ACCESS_TOKEN=your-access-token
TENCENT_DOCS_OPEN_ID=your-open-id
TENCENT_DOCS_ENCODED_ID=DRmxPc2Fob2pFb252
TENCENT_DOCS_FILE_ID=
TENCENT_DOCS_BOOK_ID=
TENCENT_DOCS_SHEET_ID=
TENCENT_DOCS_SHEET_TITLE=2026.5
TENCENT_DOCS_TAB_ID=
TENCENT_DOCS_API_BASE_URL=https://docs.qq.com
TENCENT_DOCS_SHEET_RANGE=A1:BF37
TENCENT_DOCS_READ_RANGE=A1:BF37
TENCENT_DOCS_WRITE_RANGE=B4:BF34
TENCENT_DOCS_TEMPLATE_TYPE=reagent_matrix
TENCENT_DOCS_ACTIVE_MONTH=1
TENCENT_DOCS_DEFAULT_YEAR=2026
```

注意：

- `access_token` 不是 `client_secret`，不要填到 `TENCENT_DOCS_CLIENT_SECRET`。
- Direct Token 模式下可以不配置 `TENCENT_DOCS_CLIENT_SECRET` 和 `TENCENT_DOCS_REDIRECT_URI`。
- 前端状态页只显示“已配置 / 未配置”，不会显示 `access_token`、`client_secret` 等敏感值。
- `TENCENT_DOCS_ENCODED_ID` 来自网页 URL，例如 `https://docs.qq.com/sheet/DRmxPc2Fob2pFb252?tab=000005` 中的 `DRmxPc2Fob2pFb252`。
- 后端会优先通过官方 converter 接口把 `ENCODED_ID` 转成 OpenAPI 官方 `fileID`。
- `TENCENT_DOCS_FILE_ID` 是 converter 返回的官方 fileID；如果已知，可直接配置。
- `TENCENT_DOCS_BOOK_ID` 是 sheetbook 写入接口使用的 bookID；未配置时后端默认使用解析出的官方 fileID。
- `TENCENT_DOCS_SHEET_ID` 是 OpenAPI 返回的 sheetId，推荐显式配置；未配置时后端会读取 sheet 列表自动选择。
- `TENCENT_DOCS_TAB_ID` 是旧字段兼容，不再默认信任 URL 中的 `tab=000005`。
- 读取腾讯文档使用官方 V3 路径：`GET /openapi/spreadsheet/v3/files/{fileId}/{sheetId}/{range}`。
- 写回腾讯文档使用官方 sheetbook 路径：`PUT /openapi/sheetbook/v2/{bookID}/values/{sheetId}!{range}`。

## reagent_matrix 横向矩阵模板

当前真实腾讯文档同步按《2026年化学试剂库存管理.xlsx》的横向月度矩阵解析和写回，不按普通纵向流水表处理。

- 读取范围：`A1:BF37`（含表头、A 列日期、库存行，用于导入解析）
- 写入范围：`B4:BF34`（仅数据区，31 行 × 57 列，不含表头/日期列/库存行）
- A 列：日期（日）
- 第 2 行：试剂名称，每种试剂占 3 列
- 第 3 行：`操作 / 数量 / 操作人`
- 第 4-34 行：1-31 日流水
- 第 35 行：库存汇总
- `TENCENT_DOCS_TEMPLATE_TYPE=reagent_matrix`
- `TENCENT_DOCS_READ_RANGE=A1:BF37`
- `TENCENT_DOCS_WRITE_RANGE=B4:BF34`
- `TENCENT_DOCS_ACTIVE_MONTH` 用于声明当前配置的单个 sheet 对应月份。
- 导入预检接口：`POST /api/tencent-docs/debug/import-dry-run`
- 导出预览接口：`GET /api/tencent-docs/debug/export-preview?year=2026&month=1`
- Write-Cell 测试接口：`POST /api/tencent-docs/debug/write-cell?year=2026&month=5`
- 写入前会执行维度校验（31×57）、sheetID 校验、write-cell 连通性预检

## 状态判断

`GET /api/tencent-docs/status` 会返回：

- `auth_mode`: `direct_token` 或 `oauth`
- `client_id_configured`
- `access_token_configured`
- `open_id_saved`
- `client_secret_configured`
- `redirect_uri_configured`
- `doc_id_configured`
- `ready_for_oauth`
- `ready_for_direct_token`
- `ready_for_api_endpoint`
- `encoded_id_configured`
- `file_id_resolved`
- `book_id_resolved`
- `sheet_id_resolved`
- `sheet_range_configured`
- `read_endpoint_enabled`
- `write_endpoint_enabled`
- `ready_for_import`
- `ready_for_export`
- `last_probe_error`
- `ready_for_sync`
- `token_expires_at` — Direct Token 人工维护的过期提醒时间
- `token_expiry_source` — `database` / `env` / `none`
- `token_expiry_status` — `valid` / `expiring_soon` / `expired` / `unknown`
- `token_remaining_seconds` — 距离过期的剩余秒数
- `token_remaining_text` — 中文剩余时间描述
- `token_expiring_soon` — 是否即将过期

Direct Token 模式下，凭证条件满足需要：

```text
TENCENT_DOCS_CLIENT_ID
TENCENT_DOCS_ACCESS_TOKEN
TENCENT_DOCS_OPEN_ID
TENCENT_DOCS_ENCODED_ID 或 TENCENT_DOCS_FILE_ID
```

导入腾讯文档还需要：

```text
官方 fileID 已解析
sheetID 已解析
TENCENT_DOCS_SHEET_RANGE
```

写回在线表格还需要：

```text
bookID 已解析
sheetID 已解析
TENCENT_DOCS_SHEET_RANGE
```

OAuth 模式下，`ready_for_oauth = true` 的条件是：

```text
TENCENT_DOCS_CLIENT_ID
TENCENT_DOCS_CLIENT_SECRET
TENCENT_DOCS_REDIRECT_URI
```

只有凭证、fileID/bookID、sheetID 与 range 条件满足时，`ready_for_import` / `ready_for_export` 才会为 `true`。

## 当前真实同步流程

从腾讯文档导入：

1. 后端使用 `Client-Id`、`Access-Token`、`Open-Id` 请求腾讯文档 API。
2. 按 `2026.1` 到 `2026.12` 读取历史模板 sheet。
3. 将二维表格行列转换为 `NormalizedInventoryRecord`。
4. 调用统一 `ImportService` 写入库存流水、去重并重算库存。

同步到腾讯文档：

1. 用户前端弹窗选择年份和月份（单月）或全年模式。
2. 后端根据 year/month 自动解析对应 sheet 的 sheetID（按标题匹配）。
3. 采用非破坏性增量追加方式：读取已有单元格 → 合并数据库数据 → 只写变更的 1x3 小范围。
4. 不会整块覆盖 B4:BF34，不会清空原表。
5. 全年模式会依次处理 1-12 月独立 sheet，不会把所有月份写到一个 sheet。
6. 写回失败时返回 API URL、HTTP 状态码和腾讯侧错误摘要，但不会返回 token 明文。

## 官方 sheetbook API 路径

当前真实同步不再使用旧的 `/openapi/v2/doc/sheet/update`。在线表格写回按官方 sheetbook 路径构造：

```text
GET  /openapi/sheetbook/v2/{bookID}/sheets-info
PUT  /openapi/sheetbook/v2/{bookID}/values/{range}
POST /openapi/sheetbook/v2/{bookID}/values/{range}:clear
GET  /openapi/drive/v2/files/{fileID}/metadata
GET  /openapi/drive/v2/util/converter
```

配置含义：

```env
TENCENT_DOCS_API_BASE_URL=https://docs.qq.com
TENCENT_DOCS_ENCODED_ID=DRmxPc2Fob2pFb252
TENCENT_DOCS_FILE_ID=
TENCENT_DOCS_BOOK_ID=
TENCENT_DOCS_SHEET_ID=
TENCENT_DOCS_SHEET_TITLE=
TENCENT_DOCS_TAB_ID=
```

- `TENCENT_DOCS_ENCODED_ID` 来自网页 URL，例如 `https://docs.qq.com/sheet/DRmxPc2Fob2pFb252?tab=000005` 中的 `DRmxPc2Fob2pFb252`。
- `TENCENT_DOCS_FILE_ID` 是 converter 返回的官方 fileID。为了兼容旧配置，如果 `TENCENT_DOCS_FILE_ID` 看起来像网页 encoded id，后端会按 `ENCODED_ID` 处理。
- `TENCENT_DOCS_BOOK_ID` 是 sheetbook OpenAPI 真正需要的 `bookID`；未显式配置时，后端默认使用解析出的官方 fileID。
- 正式导入/同步不再依赖固定 `TENCENT_DOCS_SHEET_ID`。后端会根据用户选择的 year/month 和 sheet 标题自动解析 sheetID。
- `TENCENT_DOCS_SHEET_ID` / `TENCENT_DOCS_TAB_ID` / `TENCENT_DOCS_ACTIVE_MONTH` 为 legacy/debug only。
- `TENCENT_DOCS_SHEET_MAP_JSON` 可选，用于显式映射 year.month → sheetID，例如 `{"2026.5":"000005"}`。
- 未配置 sheet map 时，后端会调用 spreadsheet V3 文件信息接口，按标题 `{year}.{month}` 匹配（同时兼容 `{year}.{month:02d}`、`{month}月` 等格式）。
- 前端"导入预检 / 导出预览 / Write-Cell 测试"使用页面月份输入框；正式"从腾讯文档导入 / 同步到腾讯文档"通过弹窗选择单月或全年。
## Direct Token 过期时间提醒

腾讯文档 Direct Token 模式下，系统无法从 `access_token` 本身自动解析真实过期时间。项目只保存一个人工维护的“过期提醒时间”，用于前端状态页显示和提醒，不会自动刷新 token。

可选环境变量：

```env
TENCENT_DOCS_TOKEN_EXPIRES_AT=
```

支持格式：

- `2026-06-24T23:59:59+08:00`
- `2026-06-24 23:59:59`
- `2026-06-24T23:59:59Z`

读取优先级：

1. 数据库 `system_settings` 中的 `tencent_docs_token_expires_at`
2. 环境变量 `TENCENT_DOCS_TOKEN_EXPIRES_AT`
3. 未设置

Web 后台“腾讯文档同步”页面提供“更新令牌有效期”按钮，保存后写入数据库，不会修改 `.env`，也不会返回或展示 `access_token` 明文。状态分为：`valid`、`expiring_soon`、`expired`、`unknown`。
## Write-Cell 测试

`POST /api/tencent-docs/debug/write-cell` 只用于快速验证腾讯文档写入链路，和正式月份同步无关。

默认测试目标：

```env
TENCENT_DOCS_WRITE_CELL_TEST_SHEET_ID=000001
TENCENT_DOCS_WRITE_CELL_TEST_RANGE=A1:A1
```

点击 Web 页面“Write-Cell 测试”后，后端只会写入一个单元格：`000001!A1:A1`，测试值形如 `sync_test_2026-05-25 15:04:56`。用户可以直接打开腾讯文档第一个 sheet，查看左上角 A1 是否出现测试值。正式“从腾讯文档导入 / 同步到腾讯文档”仍然根据用户选择的 year/month 自动解析对应 sheet，不会因为该测试固定到 `000001` 而改变。
