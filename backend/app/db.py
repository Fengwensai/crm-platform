from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .core.config import settings

# connect_timeout：DB 不可达时 5s 内快速失败（而不是挂住请求线程），
# 供 /api/health 健康检查快速返回 503 + db:false，避免自愈监控超时等待。
#
# 这个参数只有 PostgreSQL（psycopg）认；本地想在没装 PG 的机器上跑冒烟测试时
# 用 sqlite URL 会因不认该参数直接报错。所以按驱动判断——生产恒为 PG，
# 走的分支与改造前完全一致，不影响线上行为。
_connect_args = (
    {"connect_timeout": 5} if settings.DATABASE_URL.startswith("postgresql") else {}
)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
