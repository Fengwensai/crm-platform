"""核心回归：认证 / 数据隔断 / 填报规则 / 审计留痕。

用法（backend 目录下）：
    # 有本地 PG 时（走 .env 的 DATABASE_URL）
    .venv/Scripts/python.exe scripts/verify_core.py

    # 没 PG 也能先冒烟（用临时 sqlite，跑完删除）
    DATABASE_URL=sqlite:///./_smoke.db .venv/Scripts/python.exe scripts/verify_core.py

重点验证的是**服务端强制隔断**：员工 A 拿到自己的 token 后，无论怎么伪造参数，
都不该够得着员工 B 的数据。这是需求②的命门，前端藏按钮不算数。
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

SQLITE_SMOKE = os.environ.get("DATABASE_URL", "").startswith("sqlite")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import tuple_  # noqa: E402

import app.models  # noqa: E402,F401  确保模型注册
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.work_record import WorkRecord  # noqa: E402

PASS, FAIL = 0, []
_client = TestClient(app)
SUF = str(int(time.time()))[-6:]
MARK = f"v{SUF}"


def expect(cond, label: str, extra: str = "") -> bool:
    global PASS
    if cond:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}   {extra}")
    return bool(cond)


def body(r):
    try:
        return r.json()
    except Exception:
        return {}


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(username: str, name: str, password: str = "pass1234"):
    return _client.post(
        "/api/auth/register",
        json={"username": username, "name": name, "password": password},
    )


def login(username: str, password: str = "pass1234"):
    return _client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def main() -> int:
    Base.metadata.create_all(engine)
    print(f"=== 目标库：{'sqlite(冒烟)' if SQLITE_SMOKE else 'PostgreSQL'} | 标记 {MARK} ===\n")

    # 0) 保证有超管
    with SessionLocal() as db:
        if not db.query(User).filter(User.role == "super_admin").first():
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

    # ——— 1. 认证与审批 ———
    print("—— 认证与审批 ——")
    r = login("admin", settings.ADMIN_INIT_PASSWORD)
    expect(r.status_code == 200, "超管登录成功", f"{r.status_code} {r.text}")
    admin_tok = body(r).get("access_token", "")

    ua, ub = f"empA_{MARK}", f"empB_{MARK}"
    expect(register(ua, "员工甲").status_code == 200, "员工甲注册成功")
    expect(
        register(ua, "员工甲重复").status_code == 409, "重复工号注册被拒(409)"
    )
    expect(register(ub, "员工乙").status_code == 200, "员工乙注册成功")

    r = login(ua)
    expect(
        r.status_code == 403 and "审批" in body(r).get("detail", ""),
        "待审批账号登录被拒(403)",
        f"{r.status_code} {r.text}",
    )
    expect(login(ua, "wrongpass").status_code == 401, "密码错误登录被拒(401)")

    r = _client.get("/api/users/pending", headers=auth(admin_tok))
    pend = body(r)
    expect(
        r.status_code == 200
        and any(u["username"] == ua for u in pend)
        and any(u["username"] == ub for u in pend),
        "管理员可见待审批列表",
        str(r.status_code),
    )
    uid = {u["username"]: u["id"] for u in pend}
    a_id, b_id = uid.get(ua), uid.get(ub)

    for target, who in ((a_id, "甲"), (b_id, "乙")):
        r = _client.post(
            f"/api/users/{target}/approve", json={"note": ""}, headers=auth(admin_tok)
        )
        expect(r.status_code == 200, f"审批通过员工{who}", f"{r.status_code} {r.text}")

    r = login(ua)
    expect(r.status_code == 200, "审批后员工甲可登录", f"{r.status_code} {r.text}")
    a_tok = body(r).get("access_token", "")
    b_tok = body(login(ub)).get("access_token", "")

    # ——— 2. 项目 ———
    print("\n—— 项目 ——")
    pcode = f"PRJ_{MARK}"
    r = _client.post(
        "/api/projects",
        json={"code": pcode, "name": "标注项目甲", "unit": "条"},
        headers=auth(admin_tok),
    )
    expect(r.status_code == 201, "管理员新建项目", f"{r.status_code} {r.text}")
    pid = body(r).get("id")
    expect(
        _client.post(
            "/api/projects",
            json={"code": pcode, "name": "重复", "unit": "条"},
            headers=auth(admin_tok),
        ).status_code
        == 409,
        "重复项目编号被拒(409)",
    )
    expect(
        _client.post(
            "/api/projects",
            json={"code": f"X_{MARK}", "name": "x", "unit": "条"},
            headers=auth(a_tok),
        ).status_code
        == 403,
        "员工建项目被拒(403)",
    )

    # ——— 3. 填报规则 ———
    print("\n—— 填报规则 ——")
    from datetime import date, timedelta

    today = date.today()
    iso = lambda d: d.isoformat()  # noqa: E731

    r = _client.post(
        "/api/work-records",
        json={"project_id": pid, "work_date": iso(today), "amount": 100,
              "rework_amount": 5, "remark": "甲今天"},
        headers=auth(a_tok),
    )
    expect(r.status_code == 201, "员工甲填报今天", f"{r.status_code} {r.text}")
    a_rec = body(r).get("id")
    expect(body(r).get("qualified") == 95, "合格量 = 总量 - 返工 (100-5=95)")

    expect(
        _client.post(
            "/api/work-records",
            json={"project_id": pid, "work_date": iso(today), "amount": 50},
            headers=auth(a_tok),
        ).status_code
        == 409,
        "同一天同项目重复填报被拒(409)",
    )
    expect(
        _client.post(
            "/api/work-records",
            json={"project_id": pid, "work_date": iso(today + timedelta(days=1)),
                  "amount": 10},
            headers=auth(a_tok),
        ).status_code
        == 422,
        "填报未来日期被拒(422)",
    )
    expect(
        _client.post(
            "/api/work-records",
            json={"project_id": pid,
                  "work_date": iso(today - timedelta(days=8)), "amount": 10},
            headers=auth(a_tok),
        ).status_code
        == 422,
        "填报 8 天前被拒(422)",
    )
    r = _client.post(
        "/api/work-records",
        json={"project_id": pid, "work_date": iso(today - timedelta(days=7)),
              "amount": 77},
        headers=auth(a_tok),
    )
    expect(r.status_code == 201, "填报第 7 天(边界)允许", f"{r.status_code} {r.text}")
    expect(
        _client.post(
            "/api/work-records",
            json={"project_id": pid, "work_date": iso(today), "amount": 10,
                  "rework_amount": 999},
            headers=auth(a_tok),
        ).status_code
        == 422,
        "返工量大于总量被拒(422)",
    )

    # ——— 4. ★ 数据隔断（核心） ———
    print("\n—— ★ 数据隔断 ——")

    # 甲伪造 user_id 想给乙填数据。
    # 注意用昨天：今天甲已经有一条了，再用今天会先撞唯一约束拿到 409，
    # 那样测的就变成"重复填报"而不是"归属"，断言会假失败。
    r = _client.post(
        "/api/work-records",
        json={"project_id": pid, "work_date": iso(today - timedelta(days=1)),
              "amount": 888, "user_id": b_id},
        headers=auth(a_tok),
    )
    expect(
        r.status_code == 201 and body(r).get("user_id") == a_id,
        "★ 员工伪造 user_id 代填：记录仍归自己",
        f"{r.status_code} {r.text}",
    )
    # 再验一次反证：乙今天确实还没有这条，说明上面那 888 不是落到乙头上的
    with SessionLocal() as db:
        b_day1 = (
            db.query(WorkRecord)
            .filter(
                WorkRecord.user_id == b_id,
                WorkRecord.work_date == today - timedelta(days=1),
            )
            .count()
        )
    expect(b_day1 == 0, "★ 伪造代填没有写进他人名下(乙昨日仍 0 条)")

    # 乙也填一条，便于测试甲的可见范围
    _client.post(
        "/api/work-records",
        json={"project_id": pid, "work_date": iso(today), "amount": 321,
              "remark": "乙今天"},
        headers=auth(b_tok),
    )

    r = _client.get("/api/work-records", headers=auth(a_tok))
    rows = body(r)
    expect(
        r.status_code == 200 and all(x["user_id"] == a_id for x in rows) and len(rows) > 0,
        "★ 员工列表只含自己的记录",
        f"{r.status_code} {[x.get('user_id') for x in rows]}",
    )
    r = _client.get(f"/api/work-records?user_id={b_id}", headers=auth(a_tok))
    expect(
        all(x["user_id"] == a_id for x in body(r)),
        "★ 员工传 user_id=他人 仍只返回自己的",
        str([x.get("user_id") for x in body(r)]),
    )

    # 找到乙的记录 id，用甲的 token 去改/删
    with SessionLocal() as db:
        b_rec = (
            db.query(WorkRecord)
            .filter(WorkRecord.user_id == b_id)
            .order_by(WorkRecord.id.desc())
            .first()
        )
        b_rec_id = b_rec.id if b_rec else -1

    expect(
        _client.patch(
            f"/api/work-records/{b_rec_id}", json={"amount": 1}, headers=auth(a_tok)
        ).status_code
        == 404,
        "★ 员工改他人记录返回 404(不是403，不泄露存在性)",
    )
    expect(
        _client.delete(
            f"/api/work-records/{b_rec_id}", headers=auth(a_tok)
        ).status_code
        == 404,
        "★ 员工删他人记录返回 404",
    )
    expect(
        _client.get("/api/users", headers=auth(a_tok)).status_code == 403,
        "★ 员工访问账号列表被拒(403)",
    )
    expect(
        _client.get("/api/stats/overview", headers=auth(a_tok)).status_code == 403,
        "★ 员工访问全局统计被拒(403)",
    )
    expect(
        _client.get("/api/audit-logs", headers=auth(a_tok)).status_code == 403,
        "★ 员工访问审计日志被拒(403)",
    )

    r = _client.get("/api/stats/me", headers=auth(a_tok))
    me = body(r)
    expect(
        r.status_code == 200 and me.get("total_amount") == 100 + 77 + 888,
        "★ 员工「我的统计」只算自己",
        f"{r.status_code} total={me.get('total_amount')}",
    )

    # ——— 5. 管理者视角 + 审计 ———
    print("\n—— 管理者视角与审计 ——")
    r = _client.get("/api/work-records", headers=auth(admin_tok))
    seen = {x["user_id"] for x in body(r)}
    expect(a_id in seen and b_id in seen, "管理者可见全员数据", str(seen))

    r = _client.get("/api/stats/overview", headers=auth(admin_tok))
    ov = body(r)
    expect(r.status_code == 200 and ov.get("total_amount", 0) >= 1386,
           "管理者总览聚合正确", str(ov))

    r = _client.patch(
        f"/api/work-records/{a_rec}", json={"amount": 200}, headers=auth(admin_tok)
    )
    expect(r.status_code == 200 and body(r).get("amount") == 200,
           "管理者可修改员工数据", f"{r.status_code} {r.text}")
    expect(body(r).get("edited_by_manager") is True,
           "被管理者改过的记录带标记 edited_by_manager")

    r = _client.get("/api/audit-logs?action=修改工作数据", headers=auth(admin_tok))
    logs = body(r)
    hit = [x for x in logs if str(a_rec) == x.get("target_id")]
    expect(
        len(hit) > 0
        and hit[0]["detail"].get("before", {}).get("amount") == 100
        and hit[0]["detail"].get("after", {}).get("amount") == 200,
        "★ 审计日志含 before→after 快照",
        str(hit[:1]),
    )

    expect(
        _client.patch(
            f"/api/work-records/{a_rec}",
            json={"rework_amount": 99999},
            headers=auth(admin_tok),
        ).status_code
        == 422,
        "管理者改出「返工>总量」也被拒(422)",
    )

    # 有记录的项目不能删
    expect(
        _client.delete(f"/api/projects/{pid}", headers=auth(admin_tok)).status_code
        == 422,
        "有填报记录的项目不可删除(422)",
    )

    # ——— 6. 停用即时失效 ———
    print("\n—— 账号停用 ——")
    r = _client.patch(
        f"/api/users/{a_id}", json={"status": "disabled"}, headers=auth(admin_tok)
    )
    expect(r.status_code == 200, "管理员停用员工甲", f"{r.status_code} {r.text}")
    expect(
        _client.get("/api/stats/me", headers=auth(a_tok)).status_code == 403,
        "★ 停用后旧 token 立即失效(403)",
    )
    expect(
        _client.patch(
            f"/api/users/{a_id}", json={"status": "active"}, headers=auth(admin_tok)
        ).status_code
        == 200,
        "可重新启用",
    )

    # ——— 7. 注册限流 ———
    print("\n—— 注册限流 ——")
    limit = settings.REGISTER_RATE_LIMIT
    codes = [register(f"empR{i}_{MARK}", f"R{i}").status_code for i in range(limit - 3)]
    last = register(f"empOver_{MARK}", "over").status_code
    expect(
        last == 429,
        f"同 IP 注册超过 {limit} 次被限流(429)",
        f"前几次={codes} 最后一次={last}",
    )

    # ——— 清理 ———
    # 审计日志按「被操作对象」删，不按 summary 文本匹配：摘要是「审批通过员工 员工甲」
    # 这类中文，压根不含运行标记，只按 summary 匹配必漏（第一次跑就漏了一条
    # 「修改工作数据」）。先把要删的 id 全查出来，最后统一删日志。
    with SessionLocal() as db:
        uids = [u.id for u in db.query(User).filter(User.username.like(f"%{MARK}")).all()]
        pids = [
            p.id for p in db.query(Project).filter(Project.code.like(f"%{MARK}")).all()
        ]
        rids = (
            [r.id for r in db.query(WorkRecord).filter(WorkRecord.user_id.in_(uids)).all()]
            if uids
            else []
        )

        pairs = (
            [("work_record", str(i)) for i in rids]
            + [("user", str(i)) for i in uids]
            + [("project", str(i)) for i in pids]
        )
        if pairs:
            db.query(AuditLog).filter(
                tuple_(AuditLog.target_type, AuditLog.target_id).in_(pairs)
            ).delete(synchronize_session=False)
        if uids:
            # 员工自己填报/改自己数据若也留痕，按 actor 兜一遍
            db.query(AuditLog).filter(AuditLog.actor_id.in_(uids)).delete(
                synchronize_session=False
            )
            db.query(WorkRecord).filter(WorkRecord.id.in_(rids or [-1])).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id.in_(uids)).delete(synchronize_session=False)
        db.query(Project).filter(Project.id.in_(pids or [-1])).delete(
            synchronize_session=False
        )
        db.commit()

        left = {
            "users": db.query(User).filter(User.username.like(f"%{MARK}")).count(),
            "projects": db.query(Project).filter(Project.code.like(f"%{MARK}")).count(),
            "records": db.query(WorkRecord).filter(WorkRecord.id.in_(rids or [-1])).count(),
        }
    expect(
        left["users"] == 0 and left["projects"] == 0 and left["records"] == 0,
        "测试数据已清理干净",
        str(left),
    )

    print(f"\n{'=' * 52}")
    print(f"PASS={PASS}  FAIL={len(FAIL)}" + ("  (sqlite 冒烟)" if SQLITE_SMOKE else ""))
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  -", f)
    print("=" * 52)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
