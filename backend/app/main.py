from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .core.config import settings
from .core.deps import reject_readonly_write
from .db import SessionLocal
from .routers import (
    annotations,
    audit,
    auth,
    projects,
    qc,
    stats,
    teams,
    users,
    work_records,
)

app = FastAPI(title="客户/员工管理平台 API")

# CORS 白名单可配置：开发默认 "*" 放开，上线在 .env 的 CORS_ORIGINS 收紧为具体域名。
# 注意：通配 "*" + allow_credentials=True 是浏览器规范下的非法组合（预检会失败），
# 本项目鉴权走 Authorization header 而非 cookie，因此通配时关闭 credentials。
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False if "*" in _origins else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 只读演示账号（赛事评审用）的写操作拦截，挂在除 auth 之外的每个路由组上。
#
# ★ auth 必须排除：它里面是公开的 POST /login 与 POST /register，
#   没有 user 依赖，套上这个守卫会让包括评委在内的所有人登不进来。
#   其余路由（含 stats / audit 这种当前没有写接口的）一并挂上，是为了将来
#   往里加写接口时不用再记得补——漏挂一次就是一处绕过口子。
_readonly_guard = [Depends(reject_readonly_write)]

app.include_router(auth.router)
app.include_router(projects.router, dependencies=_readonly_guard)
# v2 双轨：标注 / 质检 + 团队
app.include_router(annotations.router, dependencies=_readonly_guard)
app.include_router(qc.router, dependencies=_readonly_guard)
app.include_router(teams.router, dependencies=_readonly_guard)
# v1 遗留路由，仍然挂载：线上库里还有旧数据要看，且迁移期两种口径并存。
# 前端已不再有入口，等确认无人再访问后可整体摘掉。
app.include_router(work_records.router, dependencies=_readonly_guard)
app.include_router(users.router, dependencies=_readonly_guard)
app.include_router(stats.router, dependencies=_readonly_guard)
app.include_router(audit.router, dependencies=_readonly_guard)

# 附件目录静态服务
MEDIA_DIR = Path(settings.MEDIA_ROOT)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    """健康检查：探测数据库连通性。DB 正常返回 200 + db:true；DB 挂返回 503 + db:false。
    供服务器自愈监控与外部探活（UptimeRobot 等）使用。

    显式声明 HEAD：FastAPI 的 APIRoute 不会像 Starlette 那样为 GET 自动补 HEAD，
    而 UptimeRobot 的 HTTP(s) 监控默认发 HEAD，缺了会收到 405 而被误判为宕机。"""
    db_ok = True
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return JSONResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "db": db_ok,
            "version": "1",
        },
        status_code=200 if db_ok else 503,
    )
