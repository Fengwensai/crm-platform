"""v2 迁移：加团队 + 双轨记录表（标注 / 质检）+ users.team_id。

**只服务已有数据的库（线上）。** 全新环境直接跑 `init_db.py` 即可。

幂等，可反复执行。**不删任何数据、不改任何现有行。**

用法（backend 目录下）：
    DATABASE_URL=... .venv/Scripts/python.exe scripts/migrate_v2.py   # Windows
    sudo -u www-data .venv/bin/python scripts/migrate_v2.py           # 服务器

————————————————————————————————————————————————————————————
为什么需要这个脚本？—— `create_all` 对已存在的表是**彻底的 no-op**。

`Base.metadata.create_all()` 只发 `CREATE TABLE`，**从不 `ALTER TABLE`**。
线上 `users` 表早就存在了，所以哪怕往 `User` 模型里加了 `team_id`，
在线上跑一百遍 `init_db.py` 也**不会**长出这一列，**而且不报错**。
索引同理。这是个静默失败，本地空库上永远复现不出来。

————————————————————————————————————————————————————————————
★ 这里的 DDL 是**从 ORM metadata 现算出来的**，不是手敲的 SQL 字符串。

理由：手敲的 DDL 一旦和模型对不上（比如忘了 `NOT NULL`、VARCHAR 长度写成 32），
线上（跑本脚本建的）与 CI（跑 `create_all` 建的）schema 就漂了，
**而 CI 永远测不出线上的差异**。从 metadata 生成，这种漂移在构造上就不存在。
配套的 `verify_schema.py` 负责在两边都验一遍。
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateColumn, CreateIndex, CreateTable  # noqa: E402

from app.db import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401  确保所有模型注册到 Base.metadata

# 迁移要用的方言：线上恒为 PostgreSQL（本地 sqlite 冒烟也用得上）
_DIALECT = postgresql.dialect()


def _ddl(stmt) -> str:
    return str(stmt.compile(dialect=_DIALECT)).strip()


def _existing_tables() -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _existing_columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def main() -> None:
    have_tables = _existing_tables()
    statements: list[str] = []
    notes: list[str] = []

    # ——— 1. 建缺的表（teams / annotation_records / qc_records）———
    for table in Base.metadata.sorted_tables:
        if table.name in have_tables:
            continue
        statements.append(_ddl(CreateTable(table, if_not_exists=True)))
        # ★ 索引必须显式建。`create_all` 对已存在的表不补索引，
        #   而这里是「表新建、但索引要一并跟上」，所以逐个发。
        statements.extend(
            _ddl(CreateIndex(ix, if_not_exists=True))
            for ix in sorted(table.indexes, key=lambda i: i.name)
        )
        notes.append(f"建表 {table.name}（含 {len(table.indexes)} 条索引）")

    # ——— 2. 给已存在的表补缺的列（users.team_id）———
    for table in Base.metadata.sorted_tables:
        if table.name not in have_tables:
            continue
        have_cols = _existing_columns(table.name)
        for col in table.columns:
            if col.name in have_cols:
                continue
            if not col.nullable and col.server_default is None:
                # 往有数据的表加 NOT NULL 且无默认值的列必然失败，
                # 与其让 PG 抛一句难懂的错，不如在这里说清楚。
                raise SystemExit(
                    f"拒绝执行：{table.name}.{col.name} 是 NOT NULL 且无默认值，"
                    f"无法安全地加到已有数据的表上。请先手工回填方案。"
                )
            statements.append(
                f"ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS "
                f"{_ddl(CreateColumn(col))}"
            )
            notes.append(f"加列 {table.name}.{col.name}")
            # 新列上的索引也要补
            for ix in sorted(table.indexes, key=lambda i: i.name):
                if col.name in {c.name for c in ix.columns}:
                    statements.append(_ddl(CreateIndex(ix, if_not_exists=True)))
                    notes.append(f"加索引 {ix.name}")

    if not statements:
        print("没有需要执行的迁移（库已是最新）。")
    else:
        print(f"将要执行 {len(statements)} 条 DDL：")
        for n in notes:
            print(f"  · {n}")
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(sa.text(stmt))
        print("迁移完成。")

    # ——— 3. 把「没做什么」也说清楚，别让数据默默消失 ———
    if "work_records" in have_tables:
        with engine.connect() as conn:
            n = conn.execute(sa.text("SELECT count(*) FROM work_records")).scalar() or 0
        if n:
            print(
                f"\n注意：旧表 work_records 里的 {n} 条 v1 记录**没有迁移**，原样留在库里。\n"
                f"      v1 是「数量 + 返工量」，v2 是「2D/3D 框数 + 质检结果」，字段口径对不上；\n"
                f"      硬迁只能编一个假的条目号和框数，它会混进「总工作量」和质检通过率的\n"
                f"      聚合里，永远洗不掉。旧表保留，随时可以 SELECT 出来对账。"
            )

    print("\n完成。别忘了：全新环境用 init_db.py；本脚本只服务于已有数据的库。")


if __name__ == "__main__":
    main()
