"""数据隔断单测：直接验 `core/scope.py` 的谓词语义，**不经过 HTTP**。

用法（backend 目录下）：
    .venv/Scripts/python.exe scripts/verify_scope.py
    DATABASE_URL=sqlite:///C:/tmp/_scope.db .venv/Scripts/python.exe scripts/verify_scope.py

————————————————————————————————————————————————————————————
为什么在 42 条 HTTP 回归之外，还要单独有这一个脚本？

`verify_core.py` 走的是端到端 HTTP，它证明的是「接口表现对」。
这个脚本走的是**谓词层**，它证明的是「隔断的定义本身对」。两者失败模式不同：

  · 端到端只覆盖到「我造出来的那几条数据」。`leaderX(team_id=NULL)` 这种
    空集边界，如果碰巧没有能匹配上的数据，**端到端会假绿**——查询返回空，
    看起来和「正确地锁死」一模一样，但其实是因为库里本来就没数据。
    这里显式地让「空集」和「本该匹配上的人」同处一库，空才说明是谓词在挡。
  · 谓词层能直接断言 `on()` 展开成哪些 user_id，不用先想好一个能触发差异的请求。

所以两个脚本都要有：一个测定义，一个测表现。
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402

import app.models  # noqa: E402,F401  确保模型注册
from app.core.scope import (  # noqa: E402
    _NO_TEAM,
    assert_can_touch,
    resolve_scope,
    visible_qc_filter,
)
from app.core.tz import now_cn, today_cn  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.annotation_record import AnnotationRecord  # noqa: E402
from app.models.qc_record import QcRecord  # noqa: E402
from app.models.team import Team  # noqa: E402
from app.models.user import User  # noqa: E402

PASS, FAIL = 0, []
SUF = str(int(time.time()))[-6:]
MARK = f"sc{SUF}"


def expect(cond, label: str, extra: str = "") -> bool:
    global PASS
    if cond:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}   {extra}")
    return bool(cond)


def mk_user(db, key: str, role: str, team_id=None) -> User:
    u = User(
        username=f"{MARK}_{key}",
        name=f"{MARK}-{key}",
        password_hash="x",  # 本脚本不登录，用不到真密码
        role=role,
        status="active",
        team_id=team_id,
    )
    db.add(u)
    db.flush()
    return u


def scope_ids(db, scope) -> list[int]:
    """把 scope 的读谓词盖在 User.id 上，看它究竟放行哪些账号。"""
    return sorted(uid for (uid,) in db.query(User.id).filter(scope.on(User.id)).all())


def main() -> int:
    Base.metadata.create_all(engine)
    print(f"=== 目标库：{'sqlite(冒烟)' if engine.dialect.name == 'sqlite' else 'PostgreSQL'}"
          f" | 标记 {MARK} ===\n")

    with SessionLocal() as db:
        # ————————————————————————————————————————————
        # 夹具：两个组 + 一个「没挂组的组长」
        # ————————————————————————————————————————————
        ta = Team(name=f"{MARK}-甲组")
        tb = Team(name=f"{MARK}-乙组")
        db.add_all([ta, tb])
        db.flush()

        leader_a = mk_user(db, "leaderA", "leader", ta.id)
        emp_a1 = mk_user(db, "empA1", "employee", ta.id)
        emp_a2 = mk_user(db, "empA2", "employee", ta.id)
        leader_b = mk_user(db, "leaderB", "leader", tb.id)
        emp_b1 = mk_user(db, "empB1", "employee", tb.id)
        # ★ 配置疏漏的化身：role 是组长，却没挂组
        leader_x = mk_user(db, "leaderX", "leader", None)
        manager = mk_user(db, "manager", "manager", None)
        boss = mk_user(db, "boss", "super_admin", None)
        db.flush()

        # ————————————————————————————————————————————
        # 1) 四种角色的范围形状
        # ————————————————————————————————————————————
        print("—— 角色 → 范围 ——")
        expect(resolve_scope(db, manager).all_, "manager 是全部范围")
        expect(resolve_scope(db, boss).all_, "super_admin 是全部范围")
        sc_a = resolve_scope(db, leader_a)
        expect(not sc_a.all_ and sc_a.team_id == ta.id, "组长 → 本组（不是全部）")
        sc_emp = resolve_scope(db, emp_a1)
        expect(
            not sc_emp.all_ and sc_emp.team_id is None,
            "员工 → 只有自己（不是全部、也不带组）",
        )

        # ★ 未知 role 值必须降级到最窄，而不是最宽
        ghost = User(username=f"{MARK}_ghost", name="?", password_hash="x", role="intern")
        sc_ghost = resolve_scope(db, ghost)
        expect(
            not sc_ghost.all_ and sc_ghost.team_id is None,
            "★ 未知角色降级为「只有自己」，不放行成全部",
        )

        # ————————————————————————————————————————————
        # 2) on() 展开成哪些账号
        # ————————————————————————————————————————————
        print("\n—— 读谓词 on() ——")
        expect(
            scope_ids(db, sc_a) == sorted([leader_a.id, emp_a1.id, emp_a2.id]),
            "组长读谓词 = 本组三人（含他自己）",
            f"实际 {scope_ids(db, sc_a)}",
        )
        expect(
            scope_ids(db, sc_emp) == [emp_a1.id],
            "员工读谓词 = 只有自己",
            f"实际 {scope_ids(db, sc_emp)}",
        )
        everyone = scope_ids(db, resolve_scope(db, manager))
        fixture_ids = [
            u.id for u in (leader_a, emp_a1, emp_a2, leader_b, emp_b1, leader_x, manager, boss)
        ]
        expect(
            set(fixture_ids) <= set(everyone),
            "管理者读谓词 ⊇ 全部夹具账号",
            f"实际 {len(everyone)} 个，缺 {sorted(set(fixture_ids) - set(everyone))}",
        )

        # ★★ 本脚本的重头戏：组长没挂组 → 空集。
        #    「返回空」和「本该返回空」必须区分开——库里此刻有 9 个活跃账号，
        #    如果谓词写错退化成全量，这里会看到 9 而不是 0。
        sc_x = resolve_scope(db, leader_x)
        expect(sc_x.team_id == _NO_TEAM, "★ 没挂组的组长走哨兵 team_id")
        expect(
            scope_ids(db, sc_x) == [],
            f"★ 没挂组的组长读谓词 = 空集（库里明明有 {len(everyone)} 个账号）",
            f"实际 {scope_ids(db, sc_x)}",
        )

        # ————————————————————————————————————————————
        # 3) covers()：写权限与读权限同源
        # ————————————————————————————————————————————
        print("\n—— 写谓词 covers() ——")
        expect(sc_a.covers(db, emp_a1.id), "组长可动本组组员")
        expect(sc_a.covers(db, leader_a.id), "组长可动自己（自己那条另有 self 分支）")
        expect(not sc_a.covers(db, emp_b1.id), "组长动不了别组组员")
        expect(not sc_a.covers(db, leader_b.id), "组长动不了别组组长")
        expect(not sc_emp.covers(db, emp_a2.id), "员工动不了同组同事")
        expect(not sc_x.covers(db, emp_a1.id), "★ 没挂组的组长谁都动不了")
        expect(
            resolve_scope(db, manager).covers(db, emp_b1.id), "管理者谁都动得了"
        )

        # ★ 读写同源：covers(u) 为真 ⟺ on() 放行的账号集合里有 u。
        #   这条断言是「物理上不可能能看不能改」的形式化版本。
        inconsistent = [
            u.id
            for u in (leader_a, emp_a1, emp_a2, leader_b, emp_b1, leader_x)
            if sc_a.covers(db, u.id) != (u.id in scope_ids(db, sc_a))
        ]
        expect(inconsistent == [], "★ 读写同源：covers 与 on 对每个账号判定一致", str(inconsistent))

        # ————————————————————————————————————————————
        # 4) assert_can_touch：越权 404，且 detail 与「不存在」逐字相同
        # ————————————————————————————————————————————
        print("\n—— 单条改/删的 404 语义 ——")
        expect(
            assert_can_touch(db, emp_a1, emp_a1.id) is False,
            "动自己的记录 → 返回 False（不需要留痕）",
        )
        expect(
            assert_can_touch(db, leader_a, emp_a1.id) is True,
            "组长动组员 → 返回 True（需要留痕）",
        )

        details = []
        for who, uid, why in (
            (emp_a1, emp_a2.id, "员工动同事"),
            (leader_a, emp_b1.id, "组长动别组组员"),
            (leader_x, emp_a1.id, "没挂组的组长动任何人"),
        ):
            try:
                assert_can_touch(db, who, uid)
                details.append(f"{why}: 没抛异常！")
            except HTTPException as e:
                details.append(f"{why}:{e.status_code}:{e.detail}")
        expect(
            all(d.endswith("404:记录不存在") for d in details),
            "★ 越权一律 404，且 detail 是同一句「记录不存在」（不是 403）",
            str(details),
        )
        # 与「ID 根本不存在」的文案对比——两者必须无法区分，否则就是存在性预言机
        try:
            assert_can_touch(db, leader_a, 999_999_999)
        except HTTPException as e:
            expect(
                e.status_code == 404 and e.detail == "记录不存在",
                "★ 「不存在」与「越权」的响应逐字相同（挡住存在性预言机）",
                f"{e.status_code}:{e.detail}",
            )

        # ————————————————————————————————————————————
        # 5) 质检可见性 = 并集（「我检的」∪「被检人在我范围内」）
        # ————————————————————————————————————————————
        print("\n—— 质检并集谓词 ——")
        # leaderA 检了本组的 empA1，又**跨组**检了乙组的 empB1
        db.add_all(
            [
                QcRecord(
                    inspector_id=leader_a.id,
                    target_user_id=emp_a1.id,
                    project_id=1,
                    qc_date=today_cn(),
                    item_no="A-1",
                    result="pass",
                ),
                QcRecord(
                    inspector_id=leader_a.id,
                    target_user_id=emp_b1.id,  # ★ 跨组
                    project_id=1,
                    qc_date=today_cn(),
                    item_no="B-1",
                    result="reject",
                ),
            ]
        )
        db.flush()

        def seen(u) -> list[str]:
            return sorted(
                r.item_no
                for r in db.query(QcRecord).filter(visible_qc_filter(db, u)).all()
            )

        expect(
            seen(leader_a) == ["A-1", "B-1"],
            "★ 质检员能看到自己**跨组**提交的那条（否则系统在否认他的提交）",
            str(seen(leader_a)),
        )
        expect(
            seen(leader_b) == ["B-1"],
            "★ 被检人的组长也能看到同一条（target 口径）",
            str(seen(leader_b)),
        )
        expect(seen(emp_a2) == [], "无关员工看不到任何质检记录")
        expect(
            sorted(seen(boss)) == ["A-1", "B-1"] or len(seen(boss)) >= 2,
            "超管能看到全部质检记录",
        )

        detail = {r.item_no: r for r in db.query(QcRecord).all()}
        expect(
            detail["B-1"].target_user_id == emp_b1.id
            and detail["B-1"].inspector_id == leader_a.id,
            "跨组那条的归属没被改写（inspector ≠ target）",
        )

        # ————————————————————————————————————————————
        # 6) 顺带的：时区助手
        # ————————————————————————————————————————————
        print("\n—— 时区 ——")
        expect(
            now_cn().utcoffset().total_seconds() == 8 * 3600,
            "now_cn() 恒为 UTC+8（不随服务器时区漂移）",
            str(now_cn().utcoffset()),
        )
        expect(today_cn() == now_cn().date(), "today_cn() 与 now_cn() 同日")

        # ————————————————————————————————————————————
        # 清理
        # ————————————————————————————————————————————
        print("\n—— 清理 ——")
        db.rollback()  # 夹具全部未提交，回滚即消失
        left = (
            db.query(User).filter(User.username.like(f"{MARK}_%")).count()
            + db.query(Team).filter(Team.name.like(f"{MARK}-%")).count()
            + db.query(QcRecord).filter(QcRecord.item_no.in_(["A-1", "B-1"])).count()
        )
        expect(left == 0, "测试数据已清理干净（未提交夹具已回滚）", f"残留 {left} 条")

    print("\n" + "=" * 52)
    if FAIL:
        print(f"PASS={PASS}  FAIL={len(FAIL)}")
        for f in FAIL:
            print(f"  [X] {f}")
        return 1
    print(f"PASS={PASS}  FAIL=0")
    print("=" * 52)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
