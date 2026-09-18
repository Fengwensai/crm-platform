from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .core.config import settings
from .db import SessionLocal
from .routers import audit, auth, projects, stats, users, work_records

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

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(work_records.router)
app.include_router(users.router)
app.include_router(stats.router)
app.include_router(audit.router)

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
