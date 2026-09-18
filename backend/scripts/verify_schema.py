"""schema 一致性检查：库里的实际结构 vs ORM 模型。

————————————————————————————————————————————————————————————
为什么需要这个脚本？

本项目有**两条建表路径**，它们建出来的表必须一模一样：

1. `init_db.py` / CI —— 走 `Base.metadata.create_all()`，结构来自 ORM。
2. `migrate_v2.py`   —— 走线上已有库的增量迁移，结构来自 metadata 现算的 DDL。

两条路径一旦漂移，**CI 永远测不出线上的差异**（CI 跑的是第 1 条）。
这个脚本的作用就是把这个差异显式地暴露出来，在两边都跑一遍。

用法（backend 目录下）：
    DATABASE_URL=... .venv/Scripts/python.exe scripts/verify_schema.py
    sudo -u www-data .venv/bin/python scripts/verify_schema.py    # 线上

退出码 0 = 一致，1 = 有差异（CI 会因此失败）。
————————————————————————————————————————————————————————————

★ 只检查**单向**：ORM 里有的表 / 列，库里必须都有且类型一致。
  **不检查库里有没有多余的东西**——旧表 `work_records` 就是故意多出来的
  （v1 遗留，保留不删），把它报成错误只会制造噪音。
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import sqlalchemy as sa  # noqa: E402

from app.db import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401  确保所有模型注册到 Base.metadata


def _type_name(t) -> str:
    """把类型编译成字符串再比。比直接比类型对象可靠——
    反射回来的类型实例往往和模型里的不是同一个对象，但编译结果一致。"""
    return str(t.compile(dialect=engine.dialect)).upper().strip()


def main() -> int:
    inspector = sa.inspect(engine)
    have_tables = set(inspector.get_table_names())
    problems: list[str] = []
    checked_tables = 0
    checked_columns = 0

    for table in Base.metadata.sorted_tables:
        if table.name not in have_tables:
            problems.append(f"缺表：{table.name}")
            continue
        checked_tables += 1
        actual = {c["name"]: c for c in inspector.get_columns(table.name)}

        for col in table.columns:
            if col.name not in actual:
                problems.append(f"缺列：{table.name}.{col.name}")
                continue
            checked_columns += 1
            a = actual[col.name]

            a_type, e_type = _type_name(a["type"]), _type_name(col.type)
            if a_type != e_type:
                problems.append(
                    f"类型不一致：{table.name}.{col.name} 库里={a_type} 模型={e_type}"
                )
            # 可空性只在一个方向上算问题：模型说 NOT NULL 而库里可空 → 约束没落到位。
            # 反过来（模型可空、库里 NOT NULL）通常是历史遗留，不算错。
            if not col.nullable and a["nullable"]:
                problems.append(
                    f"可空性不一致：{table.name}.{col.name} 模型是 NOT NULL，库里却可空"
                )

        # 索引：只查模型里显式声明的那些在不在
        have_idx = {i["name"] for i in inspector.get_indexes(table.name)}
        if engine.dialect.name == "postgresql":
            # PG 的唯一约束走的是另一套目录，反射结果不在 get_indexes 里
            have_idx |= {
                c["name"] for c in inspector.get_unique_constraints(table.name)
            }
        for ix in table.indexes:
            if ix.name not in have_idx:
                problems.append(f"缺索引：{table.name} → {ix.name}")

    print(f"检查了 {checked_tables} 张表 / {checked_columns} 个列（dialect={engine.dialect.name}）")
    if problems:
        print(f"\n发现 {len(problems)} 处不一致：")
        for p in problems:
            print(f"  [X] {p}")
        print(
            "\n修复思路：新环境看 init_db.py 是否跑过；"
            "已有数据的库看 migrate_v2.py 是否漏了 DDL。"
        )
        return 1
    # 注意：这里刻意只用 ASCII 符号。Windows 控制台默认 GBK，
    # 打 "✓" 这类字符会直接抛 UnicodeEncodeError 把脚本干掉。
    print("schema 一致 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
