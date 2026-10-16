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

> **部署状态**：v2 已上线，线上库内有一套演示数据（2 个团队、若干演示账号与填报记录），
> v1 那 1 条 `work_records` 按计划原样留着。

### 演示账号（线上环境，供评审参观）

| 用户名 | 密码 | 角色 | 可见范围 |
|---|---|---|---|
| `la` | `demo1234` | 组长 | 仅本组（梦迪组）数据 |

> 用这个账号登录最能看清本平台的核心设计——**数据隔断**：组长只能看到本组员工的填报记录，
> 看板也只统计本组，看不到其它组，更看不到全公司。
>
> 该账号**仅供赛事评审演示使用**，赛后回收。

> 全新库上 `scripts/init_db.py` 只建一个超管 `admin`，初始密码取自 `.env` 的
> `ADMIN_INIT_PASSWORD`（`.env.example` 里是 `CHANGE_ME`）——生产库的密码与仓库中任何默认值都不同。
> 员工账号由本人自助注册、管理者审批后启用。

---

## 三条核心需求 → 实现位置

| 需求 | 落在哪 |
|---|---|
| ① 数据填写：每个用户填自己的工作数据 | `frontend/src/views/AnnotationWork.vue` / `QcWork.vue` + `backend/app/routers/{annotations,qc}.py` |
| ② 数据隔断：只能操作自己（组长：本组）的数据 | `backend/app/core/scope.py` —— **可见性只有一处定义**，读与写都从它派生 |
| ③ 数据分析：管理者看全公司、组长看本组 | `backend/app/routers/stats.py` + `frontend/src/views/Dashboard.vue` |

## 双轨数据模型

一条工作线拆成两条轨，**永不合并成一个「总产出」数字**（框数和质检条数是不同量纲，
相加没有意义）：

| 轨 | 记什么 | 工作量口径 |
|---|---|---|
| **标注** `annotation_records` | 条目号 + 2D 框数 + 3D 框数 | `box2d + box3d` |
| **质检** `qc_records` | 被质检人员 + 条目号 + 通过/打回 | 条数；通过率 = 通过 / 总数 |

- 同人 + 同项目 + 同天 + 同条目号**允许重复登记**（真实场景里同一批分几次做很常见），
  只提示「疑似重复」，**从不拦**。所以重复登记返回 **201**，不是 409。
- 质检的**通过率**按 `(project_id, item_no)` 分组——条目号是项目内编号，
  项目 A 的 `123` 和项目 B 的 `123` 是两回事。
- v1 的 `work_records`（数量 + 返工量）**表保留、模型保留、统计里已彻底摘掉**——
  v2 的所有列表、看板、导出都不读它。它不迁移：字段口径对不上（旧行里 `item_no/box2d/box3d`
  一个都没有），硬迁只能编假数据，而假数据会永远混在「总工作量」与通过率聚合里洗不掉。
  > ⚠️ **现状说明**：旧的 `/api/work-records` 接口**仍然挂载着**（线上库里还有 v1 数据要能看），
  > 只是前端已无任何入口。它写出来的记录**不会出现在 v2 的任何视图里**——所以不要用它登记新数据。
  > 要不要摘掉这个路由器，等确认无人再访问后单独决定（见文末「已知遗留」）。

## 数量口径里没有「单位」

项目表上有 `unit` 列，那是 v1 遗留。v2 的数量口径是 2D/3D **框数**，单位恒为「框」，
所以 `unit` 已从**接口入参、响应、后台表单、看板**中全部移除，只有列本身还留在库里
（`DROP COLUMN` 不可逆，而一个空列的存续成本是零）。

留着它的害处不是浪费一次输入：后台里会有人继续维护「条 / 句 / 张」，而那些值
不会被任何一处读取——填的人以为它有意义，看到的人以为它是真的。

## 规则约定

| 项 | 规则 |
|---|---|
| 角色 | `employee` 员工 / `leader` 组长 / `manager` 管理者 / `super_admin` 超管 |
| 账号来源 | 员工自助注册 → 管理者审批通过才能登录 |
| 组长 | **必须有团队，且一个团队只能有一个组长**（两个字段合起来校验）。团队表上**没有** `leader_id`，组长身份只由 `User.role` 决定 |
| 填报限制 | 不能填未来（对所有人）；只能填最近 **7 天**内（`BACKFILL_DAYS`），**组长与管理者豁免该窗口** |
| 标注重复 | 允许，只提示 |
| 质检 | 不能质检自己（422）；被质检人员**全员可选**（跨组质检是常态） |
| 代填 | 员工传他人 `user_id` → **404**；组长传本组 → 201 归组员 + 留痕；传别组 → 404 |
| 改数据 | 组长可改/删**本组**组员的记录，管理者可改/删全部；写审计日志（含改前→改后快照），记录标 `edited_by_manager` |
| 删数据 | 有标注 / 质检 / v1 填报记录的账号与项目**删不掉**，提示改用停用/归档；有成员的团队删不掉 |

### ② 是怎么保证的

不靠前端，全部在服务端，且**只在一处定义**（`core/scope.py`）：

- 列表的 SQL 过滤与单条的「能不能改」从**同一个谓词**派生，
  所以物理上不可能出现「列表过滤对了但单条忘了判权限」
- scope **永远第一个盖上去**；用户传的 `user_id` 只能在它之上再收窄，
  `?user_id=<别组的人>` 的结果是**空列表**，不可能放大范围
- 组长 `team_id=NULL`（配置疏漏）解析成**空集**，绝不退化成「看到全公司」；
  未知 role 一律降级为最窄
- 停用账号后，**手上已签发的 token 立刻失效**（不是等重新登录）

### 404 / 403 规则表

**本平台的铁律：越权一律 404，不用 403。** 403 等于承认「这条记录存在」，
拿不同的 ID 去试就能反推出库里的记录分布——一个免费的存在性预言机。

| 场景 | 码 | 说明 |
|---|---|---|
| 列表：范围外的行 | 不返回 | 静默过滤掉，**不是 403** |
| 改/删：ID 不存在 | 404 | detail = `记录不存在` |
| 改/删：存在但超范围 | **404** | detail 与上一条**逐字相同**，两条路径合并成一个 `raise` |
| create 带了越权 `user_id` | **404** | detail = `指定的员工不存在` |
| 打管理者专属端点 | 403 | `require_manager`；`leader` 不属于管理者，被自动挡住 |

★ **范围检查必须早于一切因数据内容而异的校验**。把「条目号不能为空」这类 422
插到 404 之前，「越权 + 空条目号 → 422」和「越权 + 正常条目号 → 404」就构成了预言机。

## 菜单与路由：一份数组驱动两边

`frontend/src/constants/nav.js` 的 `NAV` 是菜单与路由的**唯一真相源**，`router/index.js`
用它生成 children + `meta.roles`，`AppLayout.vue` 用它渲染菜单。

不这样写的话，两处各写一遍权限，结果必然是**「菜单藏了但 URL 还能直接进」**——
而这种漏法不报错：组长手敲 `/users` 就进去了，页面上还都是他能看的数据，没人会发现。
`roles` 是**白名单**（谁能进），新增角色默认什么都不给。

| 角色 | 菜单 |
|---|---|
| `employee` | 标注工作量登记、质检工作量登记 |
| `leader` | 上面 + 数据看板 |
| `manager` / `super_admin` | 全部 5 项（+ 用户管理里的团队、操作留痕两个 tab） |

前端这套只是**体验层**的收口，不是安全边界——真正的隔断在服务端（见上面那张 404 表）。

## 目录

```
backend/
  app/core/       配置、鉴权、限流、审计、客户端 IP、时区、**scope（数据隔断）**、guards（删除守卫）
  app/models/     user / team / project / annotation_record / qc_record / audit_log / work_record(v1 遗留)
  app/routers/    auth / users / teams / projects / annotations / qc / stats / audit
  app/services/   export.py（CSV 导出，复制自方言平台）
  scripts/        init_db.py（建表+种子超管）、migrate_v2.py（线上增量迁移，幂等）、
                  verify_core.py / verify_scope.py / verify_schema.py（三条回归）、
                  backup.sh（每日备份）、e2e_http.sh（走公网的端到端冒烟）
frontend/         Vue3 + Element Plus + Vite，浅色主题
  src/constants/nav.js   菜单 + 路由的唯一真相源
  src/components/        RecordHistory.vue（改动前→后弹窗）、TrendBars.vue（手绘双轨柱图）
  src/views/             AnnotationWork / QcWork / Dashboard / UserManage / ProjectManage
  src/views/users/       UserManage 的四个 tab：TabPending / TabAccounts / TabTeams / TabAudit
```

> v1 的 `MyWork.vue` / `MyStats.vue` / `AllRecords.vue` / `AccountReview.vue` / `AuditLog.vue`
> **文件已删除**（不是从菜单里藏起来）。藏起来的话，`import` 还编得过，代码会一直躺在那里
> 继续被引用；删掉文件，任何残留引用都会当场编译失败。它们的去处：
> 员工填报/统计 → 两个记录页按角色收窄；全部数据 → 两个记录页对管理者天然不加范围；
> 账号审批 / 操作留痕 → 用户管理页的两个 tab。


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

三条，**互不替代**：

```bash
cd backend

# ① 核心回归（149 项断言）：认证审批 / 团队与角色 / 标注 / 质检 / 数据隔断 /
#    代填归属 / 导出 / 统计 / 停用即时失效 / 注册限流。
#    没装 PG 时可先用 sqlite 冒烟（脚本自己建表 + 自己清理）：
DATABASE_URL=sqlite:///./_smoke.db ./.venv/Scripts/python.exe scripts/verify_core.py

# ② 隔断谓词单测（30 项断言）：直接验 core/scope.py 的读写语义，不经 HTTP。
#    专测端到端会「假绿」的边界——leader 没挂组 → 空集（库里本来就没数据，
#    返回空看起来和正确地锁死一模一样）。
.venv/Scripts/python.exe scripts/verify_scope.py

# ③ schema 一致性：库里的实际结构 vs ORM 模型（见下「两条建表路径」）。
#    只在真 PG 上有意义，且必须在 migrate_v2.py 跑过之后跑。
.venv/Scripts/python.exe scripts/verify_schema.py

# 服务器上跑（真 PG）。HOME=/tmp 是为了避开 www-data 家目录不可写的告警；
# PYTHONIOENCODING=utf-8 必须带——断言标题是中文，locale 不是 UTF-8 时会直接炸在 print 上。
cd /opt/crm/backend && sudo -u www-data HOME=/tmp PYTHONIOENCODING=utf-8 \
  .venv/bin/python scripts/verify_core.py

# ④ 走公网域名的端到端（8 项）：验 nginx / TLS / Authorization 透传、
#    建项目 → 登记标注 → 统计卡计入、★「不存在的记录 → 404 而不是 403」。
#    只能在服务器上跑（要用 --resolve 绕开服务器没有 hairpin NAT 这件事）。
bash scripts/e2e_http.sh
```

`verify_core.py` 会自建测试数据并在结束前清理干净（含审计日志、标注、质检、团队），
并在最后断言清理结果。

### 两条建表路径（本仓最容易静默出错的一处）

| 路径 | 用在哪 | 结构来自 |
|---|---|---|
| `Base.metadata.create_all()` | 全新环境、CI、`init_db.py` | ORM 模型 |
| `scripts/migrate_v2.py` | **线上已有数据的库** | 从 ORM metadata **现算**的裸 DDL |

★ `create_all()` 对**已存在的表是彻底的 no-op**——只 `CREATE TABLE`，从不 `ALTER TABLE`，
**而且不报错**。所以往模型里加了列（比如 `users.team_id`）之后，在线上跑一百遍
`init_db.py` 也不会长出这一列。这就是 `migrate_v2.py` 存在的唯一理由。

★ 两条路径一旦漂移，**CI 永远测不出线上的差异**（CI 跑的是第一条）。所以 CI 的顺序是
**先 `migrate_v2.py`（两遍，验幂等）→ 再 `verify_schema.py` → 最后才是两条回归**。
顺序写反，迁移脚本的 bug 永远进不了 CI。

★ `migrate_v2.py` **只对 PostgreSQL 生成 DDL**（写死 `postgresql.dialect()`），
连到别的方言会直接拒绝执行。这是有意的：它的产物要落到线上，不能因为有人把
`DATABASE_URL` 指错了库就换一套语法，悄悄建出一份半成品 schema。

## 部署

后端改完要**重启服务**才生效（`.env` 是启动时加载的）。

**顺序：先把两个包都传到 `/tmp` → 再一次性换掉前后端 → 最后重启。**
不先把包传完的话，「后端是新的、前端还是旧的」这个窗口会持续整个上传时间；
传完之后动手，窗口只有几秒。

```bash
# ── ① 本地打包 + 上传 ────────────────────────────────────────────
cd backend && tar -czf /tmp/crm-backend.tar.gz --exclude='__pycache__' app scripts requirements.txt
cd ../frontend && npm run build && tar -czf /tmp/crm-frontend.tar.gz -C dist .
scp /tmp/crm-backend.tar.gz /tmp/crm-frontend.tar.gz root@182.92.9.204:/tmp/

# ── ② 服务器上：留回滚点 → 迁移 → 换后端 → 换前端 → 重启 ──────────
ssh root@182.92.9.204
cd /opt/crm/backend
TS=$(date +%Y%m%d-%H%M%S)
tar -czf /tmp/crm-prev-backend-$TS.tar.gz  --exclude=__pycache__ app scripts
tar -czf /tmp/crm-prev-frontend-$TS.tar.gz -C /opt/crm/frontend/dist .

# ★ 必须排在解包**之后**：这个脚本是随 `scripts/` 一起部署的，
#   在此之前服务器上跑的是上一版（新服务器上则是根本没有这个文件）。
cp -a .env /tmp/k && rm -rf app scripts \
  && tar -xzf /tmp/crm-backend.tar.gz -C /opt/crm/backend && cp -a /tmp/k .env && rm /tmp/k \
  && chown -R www-data:www-data app scripts requirements.txt .env
sudo -u www-data HOME=/tmp .venv/bin/python scripts/migrate_v2.py   # 幂等，见「两条建表路径」

rm -rf /opt/crm/frontend/dist && mkdir -p /opt/crm/frontend/dist \
  && tar -xzf /tmp/crm-frontend.tar.gz -C /opt/crm/frontend/dist \
  && chown -R www-data:www-data /opt/crm/frontend/dist

systemctl restart crm-api && sleep 3 && systemctl is-active crm-api

# ── ③ 验 ────────────────────────────────────────────────────────
sudo -u www-data HOME=/tmp .venv/bin/python scripts/verify_schema.py
sudo -u www-data HOME=/tmp .venv/bin/python scripts/verify_core.py   # 149 项
sudo -u www-data HOME=/tmp .venv/bin/python scripts/verify_scope.py  # 30 项
bash scripts/e2e_http.sh
```

**回滚**：把 ② 里那两个 `crm-prev-*.tar.gz` 原样解回去再重启即可
（后端回滚同样要保留 `.env`）。

> ⚠️ `rm -rf scripts` 会连 `backup.sh` 一起删掉（`/etc/cron.d/crm-backup` 每日 03:37 依赖它）。
> 仓库里的 `scripts/backup.sh` 就是线上那份的正本，已随包一起传（2026-09-18 部署时逐字节比对确认一致）；
> 但**改过线上备份脚本而没同步回仓库**的话，这一步会把它覆盖掉。

## 运维备忘

- 服务：`systemctl status crm-api`（127.0.0.1:8001，`MemoryMax=512M` 防拖垮同机的方言平台）
- 库：`sudo -u postgres psql -d crm_admin`，角色 `crm`
- 备份：`/etc/cron.d/crm-backup` → 每日 03:37 跑 `scripts/backup.sh`（与方言平台 03:17 错开）
  → 落在 `/data/crm/backups`，日志 `/var/log/crm-backup.log`
  （★ 它是 **cron.d 里的系统任务，不是 `crontab -l`**——用 `crontab -l` 查会得到
  「no crontab for root」，看着像备份没配，实际是有的）
- 密钥：`/deploy-bundle/CRM_SECRETS.txt`（root 600）与 `/opt/crm/backend/.env`
- 服务器**没有 hairpin NAT**：在服务器上自测要走
  `curl --resolve crm.qlzby.com:443:127.0.0.1 https://crm.qlzby.com/`，直连公网 IP 会失败
- **nginx：两个平台共用一份全局配置**，改一处两边都受影响——动它之前先想清楚这点。
  2026-09-18 为首屏提速动过两处；改动前的原件留在服务器
  `/root/nginx-backup-20260918-175822/`，同目录的 `README.txt` 写明哪个文件能拿来回滚、哪个不能。

  | 文件 | 改动 | 为什么 |
  |---|---|---|
  | `/etc/nginx/nginx.conf` | 打开 `gzip_types` 等 5 条 | 原本只有 `gzip on;`，而 `gzip_types` 是注释掉的，nginx 默认**只压 `text/html`**，打包产物一个字节都不压。实测 JS **1,267,421 → 408,852 字节**，首屏 **8~9 秒 → 2.03 秒** |
  | `sites-available/crm.conf` | 新增 `location /assets/` | Vite 产物名带内容哈希，可以安全长缓存 |

  ★ **别把 `gzip_types` 注释回去**。只留 `gzip on;` 看起来像「压缩开着」，实际 JS/CSS/JSON 全是裸传，
  而且**不报任何错**——这正是它被漏掉这么久的原因。判断是否真的生效要看响应头有没有 `Content-Encoding`，
  不是看 `gzip on` 在不在。

  ★ `index.html` **刻意不设** `Cache-Control`，让它每次都协商（304）：发版后浏览器立刻拿到新 HTML，
  再由新 HTML 去取新的哈希文件名。要是给 `index.html` 也加长缓存，用户会一直停在旧版本，
  而且**刷新也没用**，只能清浏览器缓存——这个坑比多几次 304 贵得多。

  ★ **别照搬给方言平台的门户**：`/opt/portal/assets/` 下是 `css/ js/ images/` 这类**手工维护、
  文件名不带哈希**的目录，给它加 `immutable` 会让改过的文件在回访用户那里一年都不更新。
  长缓存的前提是**文件名随内容变**；不满足这个前提时，正确做法是不加。

## 已知遗留

不是待办清单，是**几处「知道不对但有意先不动」**的地方，免得下一个人以为是漏了：

| 遗留 | 现状与理由 |
|---|---|
| `/api/work-records` 路由仍挂载 | 前端已无入口，但它写出的记录**不进 v2 的任何统计**。摘它要连带改掉一条 v1 回归（那条回归同时在验「v1 记录也算数」的删除守卫），留到确认无人访问后一起做 |
| `projects.unit` 列 | v1 遗留。接口/界面/统计都读不到它，只是列还在库里 |
| `work_records` 表与模型 | 线上还有 v1 数据。模型必须继续留在 `models/__init__.py` 里，否则 `create_all` 在新环境不会建它，schema 会漂 |
| 打包命令里的 `rm -rf scripts` | 会连 `backup.sh` 一起删（`/etc/cron.d/crm-backup` 依赖它）。仓库里那份已随包部署并逐字节核对过，但「在服务器上直接改备份脚本」这个习惯会让它被悄悄覆盖——改备份要改仓库那份再部署 |
| `/etc/nginx/` 不在仓库里 | nginx 配置是纯手工的服务器状态：部署只换 `app/`、`scripts/`、`dist/`，没有任何一步会碰它。好处是**不会被部署覆盖**，代价是**也不会被备份和 git 带走**——改之前先 `cp -L` 存一份（★ 必须带 `-L`，`sites-enabled/` 下全是符号链接，不加的话备份出来还是指回原文件的链接，等于没存） |

