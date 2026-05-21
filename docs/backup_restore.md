# 数据备份、恢复与回滚策略

## 一、备份层次概览

| 层次 | 负责方 | 频率 | 覆盖范围 |
|------|--------|------|---------|
| Supabase 平台备份 | Supabase（自动） | 每日 | 全库 PITR |
| 项目级 JSON 备份 | 开发者手动/定时 | 按需 | 6 张核心表 |
| Render 环境变量备份 | 开发者手动 | 配置变更时 | 环境变量清单 |
| Cloudflare Pages 历史 | Cloudflare（自动） | 每次部署 | 前端构建 |

---

## 二、Supabase 平台备份

1. 登录 [Supabase Dashboard](https://supabase.com/dashboard)
2. 进入项目 → Settings → Database → Backups
3. 查看自动备份列表（Pro 计划支持 PITR 时间点恢复）
4. Free 计划不包含自动备份，**必须依赖项目级 JSON 备份**

---

## 三、项目级备份执行

### 3.1 试运行（查看表结构）

```bash
cd backend
python backup_postgres_data.py --dry-run
```

### 3.2 正式备份

```bash
cd backend
python backup_postgres_data.py
```

输出：`backups/pg_backup_YYYYMMDD_HHMMSS.json`

### 3.3 备份包含的表

| 表 | 内容 | 备注 |
|----|------|------|
| `users` | 用户账号 | 含 password_hash，不含明文密码 |
| `reagents` | 试剂库存 | 19 种预置试剂 + 自定义 |
| `inventory_records` | 库存流水 | 出入库记录、操作员 |
| `alert_events` | 报警事件 | 低库存/过期报警 |
| `sync_logs` | 同步日志 | 腾讯文档同步历史 |
| `audit_logs` | 审计日志 | 操作审计记录 |

---

## 四、恢复演练

### 4.1 Dry-run（校验备份文件，不写入）

```bash
cd backend
python restore_postgres_data.py --file backups/pg_backup_YYYYMMDD_HHMMSS.json --dry-run
```

### 4.2 空库恢复

```bash
# 1. 确认目标库为空
python check_postgres_smoke.py --live

# 2. 执行恢复
python restore_postgres_data.py --file backups/xxx.json --confirm-restore

# 3. 校准 sequence（脚本自动完成）
# 4. 校验
python check_postgres_smoke.py --live
```

### 4.3 强制覆盖恢复（危险）

```bash
python restore_postgres_data.py --file backups/xxx.json --confirm-restore --force
```

> 此操作会覆盖已有数据，执行前系统会提示二次确认。

---

## 五、Render 后端回滚

1. 登录 Render Dashboard → Web Service
2. 进入 Settings → "Deploy" → "Deploy Hooks" 或查看部署历史
3. 在 "Manual Deploy" 中选择之前的 Git commit → "Deploy"
4. 如果需要回滚到特定版本：
   - 找到对应的 GitHub commit hash
   - Render → Manual Deploy → "Deploy a specific commit"
   - 输入 commit hash → Deploy

### 回滚后数据库迁移注意

如果回滚涉及数据库模型变更：
- Render 不会自动回滚数据库迁移
- 需要手动执行 `python -m alembic downgrade -1` 回退迁移

---

## 六、Cloudflare Pages 前端回滚

1. 登录 Cloudflare Dashboard → Workers & Pages
2. 选择项目 → "Deployments"
3. 查看部署历史列表
4. 点击历史部署右侧的 "..." → "Rollback to this deployment"
5. 确认回滚

---

## 七、数据库误操作处理

### 场景 1：误删记录

1. 确定误操作时间
2. 如果有 Supabase PITR（Pro 计划）：联系 Supabase 恢复
3. 如果没有 PITR：从最近的项目级 JSON 备份恢复

```bash
python restore_postgres_data.py --file backups/pg_backup_<最新>.json --confirm-restore --force
```

### 场景 2：误改表结构

1. 使用 Alembic 回退迁移：

```bash
python -m alembic downgrade -1
```

2. 或查看迁移历史，回退到指定版本：

```bash
python -m alembic history
python -m alembic downgrade <revision_id>
```

### 场景 3：误清空表数据

1. 不要关闭数据库连接
2. 立即从备份恢复到临时表
3. 将数据从临时表迁移回原表

---

## 八、备份频率建议

| 环境 | 频率 | 方式 |
|------|------|------|
| 生产 | **每日** | `python backup_postgres_data.py` + cron |
| 生产 | 重大变更前 | 手动备份 |
| 开发 | 按需 | `python backup_postgres_data.py` |

---

## 九、备份文件安全

- 备份文件路径：`backend/backups/`
- 已加入 `.gitignore`，不会提交到 Git
- 备份文件包含 `password_hash`（bcrypt 哈希），不含明文密码
- 建议将备份文件定期同步到安全的云存储
