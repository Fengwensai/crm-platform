# 工作量统计平台

数据标注公司内部用：员工每天填报各项目的标注量，管理者看整体走向。
替代原先的共享表格——共享表格的问题是**低效**（每人一份、汇总靠手工）和**不安全**
（谁改了什么无人知晓）。

线上地址：

| 用途 | 地址 |
|---|---|
| 后台（员工填报 + 管理端） | https://crm.qlzby.com |
| 后端 API | https://crm-api.qlzby.com |

与方言采集平台**同机部署**（同一台 ECS），但库、进程、证书、目录全部独立。

---

## 三条核心需求 → 实现位置

| 需求 | 落在哪 |
|---|---|
| ① 数据填写：每个用户填自己的工作数据 | `frontend/src/views/MyWork.vue` + `backend/app/routers/work_records.py` |
| ② 数据隔断：只能操作自己的数据，看不到也改不了别人的 | `backend/app/routers/work_records.py` 的**服务端强制过滤**（前端藏按钮不算数） |
| ③ 数据分析：管理者看整体走向 | `backend/app/routers/stats.py` + `frontend/src/views/Dashboard.vue` |

### ② 是怎么保证的

不靠前端，全部在服务端：

- 员工查列表时**无条件**盖掉 `user_id` 过滤条件（不是"没传才过滤"）
- 员工伪造 `user_id` 提交，记录仍归自己（服务端忽略该字段）
- 员工改/删他人记录返回 **404 而非 403**——403 等于承认"这条存在"
- 员工打 `/api/users`、`/api/stats/overview`、`/api/audit-logs` 一律 403
- 停用账号后，**手上已签发的 token 立刻失效**（不是等重新登录）

## 规则约定

| 项 | 规则 |
|---|---|
| 角色 | `employee` 员工 / `manager` 管理者 / `super_admin` 超管 |
| 账号来源 | 员工自助注册 → 管理者审批通过才能登录 |
| 填报限制 | 只能填最近 **7 天**内、不能填未来（`BACKFILL_DAYS`），员工在此窗口外不可改 |
| 唯一性 | 同一人 + 同一项目 + 同一天只能一条 |
| 字段 | 数量 + 返工量（合格量 = 数量 − 返工量）+ 备注 |
| 管理者改数据 | 允许，但写审计日志（含改前→改后快照），记录标 `edited_by_manager`，员工端可见 |
| 删数据 | 管理者可删（留痕）；有填报数据的账号/项目删不掉，提示改用停用/归档 |

## 目录

```
backend/
  app/core/       配置、鉴权、限流、审计、客户端 IP
  app/models/     user / project / work_record / audit_log
  app/routers/    auth / users / projects / work_records / stats / audit
  scripts/        init_db.py（建表+种子超管）、verify_core.py（回归）、
                  backup.sh（每日备份）、e2e_http.sh（走公网的端到端冒烟）
frontend/         Vue3 + Element Plus + Vite，深色主题与方言平台一致
```

## 本地开发

```bash
# 后端（本地 PG 需先建库：psql -U postgres -f backend/scripts/create_db.sql）
cd backend
./.venv/Scripts/python.exe scripts/init_db.py
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# 前端（vite 代理 /api → 127.0.0.1:8001）
cd frontend && npm install && npm run dev   # http://localhost:5174
```

## 回归测试

```bash
# 完整回归（42 项断言）。没装 PG 时可先用 sqlite 冒烟：
cd backend
DATABASE_URL=sqlite:///./_smoke.db ./.venv/Scripts/python.exe scripts/verify_core.py

# 服务器上跑（真 PG）
cd /opt/crm/backend && sudo -u www-data .venv/bin/python scripts/verify_core.py

# 走公网域名的端到端（验 nginx / TLS / Authorization 透传）
bash scripts/e2e_http.sh
```

`verify_core.py` 会自建测试数据并在结束前清理干净（含审计日志），并在最后断言清理结果。

## 部署

后端改完要**重启服务**才生效（`.env` 是启动时加载的）：

```bash
# 本地：打包 → 上传 → 解包（保留服务器上的 .env）→ 重启
cd backend && tar -czf /tmp/crm-backend.tar.gz --exclude='__pycache__' app scripts requirements.txt
scp /tmp/crm-backend.tar.gz root@182.92.9.204:/tmp/
ssh root@182.92.9.204 'cd /opt/crm/backend && cp -a .env /tmp/k && rm -rf app scripts \
  && tar -xzf /tmp/crm-backend.tar.gz -C /opt/crm/backend && cp -a /tmp/k .env && rm /tmp/k \
  && chown -R www-data:www-data app scripts requirements.txt .env && systemctl restart crm-api'

# 前端：npm run build → 传 dist → /opt/crm/frontend/dist
```

> ⚠️ `rm -rf scripts` 会连 `backup.sh` 一起删掉（每日 03:37 的备份 cron 依赖它），
> 解包前务必确认备份脚本在包里或单独补传。

## 运维备忘

- 服务：`systemctl status crm-api`（127.0.0.1:8001，`MemoryMax=512M` 防拖垮同机的方言平台）
- 库：`sudo -u postgres psql -d crm_admin`，角色 `crm`
- 备份：每日 03:37（与方言平台 03:17 错开）→ `/data/crm/backups`
- 密钥：`/deploy-bundle/CRM_SECRETS.txt`（root 600）与 `/opt/crm/backend/.env`
- 服务器**没有 hairpin NAT**：在服务器上自测要走
  `curl --resolve crm.qlzby.com:443:127.0.0.1 https://crm.qlzby.com/`，直连公网 IP 会失败
