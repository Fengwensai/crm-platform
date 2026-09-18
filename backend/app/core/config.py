from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # PostgreSQL 连接串，形如 postgresql+psycopg://crm:<密码>@127.0.0.1:5432/crm_admin
    DATABASE_URL: str
    # 后台登录 JWT 签名密钥（上线务必用随机长串）
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 720
    # 种子管理员初始密码（init_db.py 建 admin 用）。默认 admin123 便于本地联调，
    # 上线务必在 .env 设强密码再跑 init_db.py。
    ADMIN_INIT_PASSWORD: str = "admin123"
    # 上传附件根目录（默认 backend/media，可通过 .env 的 MEDIA_ROOT 覆盖）
    MEDIA_ROOT: str = str(BASE_DIR / "media")
    # CORS 白名单，逗号分隔；开发默认 "*" 便于联调，上线在 .env 收紧为
    # https://crm.qlzby.com（与 dialect 平台同一套写法）。
    CORS_ORIGINS: str = "*"
    # —— 填报规则 ——
    # 员工只能填报/修改最近 N 天内的数据，且不能填未来（防翻旧账乱改历史）。
    # 管理者不受此限（其修改另有审计日志留痕）。
    BACKFILL_DAYS: int = 7
    # —— 限流（进程内固定窗口，防刷/防爆破）——
    # 注册接口是公开的（无需登录），必须限频；同 IP 每窗口最多 N 次。
    REGISTER_RATE_LIMIT: int = 5
    REGISTER_RATE_WINDOW_SECONDS: int = 3600
    # 登录尝试：同 IP 每窗口最多 N 次（无论成败）
    LOGIN_RATE_LIMIT: int = 30
    LOGIN_RATE_WINDOW_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
    )


settings = Settings()
