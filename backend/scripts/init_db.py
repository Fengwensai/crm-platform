"""建表 + 种子超管。幂等：可在任意环境反复执行。

用法（backend 目录下）：
    .venv/Scripts/python.exe scripts/init_db.py      # Windows 本地
    ./.venv/bin/python scripts/init_db.py            # 服务器

超管账号 admin，密码取 .env 的 ADMIN_INIT_PASSWORD。
已存在超管时**不改密码**（避免误重置线上账号）；要改密码去后台「账号管理」。
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.user import User  # noqa: E402
import app.models  # noqa: E402,F401  确保所有模型注册到 Base.metadata


def main() -> None:
    Base.metadata.create_all(engine)
    print("建表完成：users / projects / work_records / audit_logs")

    with SessionLocal() as db:
        existing = db.query(User).filter(User.role == "super_admin").first()
        if existing is not None:
            print(f"超管已存在（{existing.username}），跳过创建，密码保持不变")
            return
        db.add(
            User(
                username="admin",
                name="超级管理员",
                password_hash=hash_password(settings.ADMIN_INIT_PASSWORD),
                role="super_admin",
                status="active",
            )
        )
        db.commit()
        print("已创建超级管理员：账号 admin，密码取 .env 的 ADMIN_INIT_PASSWORD")


if __name__ == "__main__":
    main()
