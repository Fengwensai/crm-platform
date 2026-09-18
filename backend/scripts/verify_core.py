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
from sqlalchemy import func, tuple_  # noqa: E402

import app.models  # noqa: E402,F401  确保模型注册
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.tz import today_cn  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.annotation_record import AnnotationRecord  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.qc_record import QcRecord  # noqa: E402
from app.models.team import Team  # noqa: E402
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


def mk_user(username: str, name: str, role: str, team_id: int | None = None) -> int:
    """**直接入库**造账号（团队/角色夹具专用），不走 `/api/auth/register`。

    ★ 为什么不走注册接口：注册是**按 IP 限流**的（每窗口 5 次），而下面
      「注册限流」那一组断言把配额吃满了。走接口造 7 个夹具账号的结果是夹具
      先被 429 挡掉，然后限流断言拿到一个「前几次里已经有 429」的错乱状态——
      两组测试互相污染，而且失败信息指向完全无关的地方。

      直接入库还把「造夹具」与「测注册」两件事彻底分开：夹具不需要验注册流程，
      注册流程有自己的断言。
    """
    with SessionLocal() as db:
        u = User(
            username=username,
            name=name,
            password_hash=hash_password("pass1234"),
            role=role,
            status="active",
            team_id=team_id,
        )
        db.add(u)
        db.commit()
        return u.id


def tok(username: str) -> str:
    """夹具账号（密码恒为 pass1234）的 token。"""
    return body(login(username)).get("access_token", "")


def csv_rows(resp) -> list[str]:
    """CSV 响应体去掉 BOM 后按行切开，供断言行数用。"""
    text = resp.content.decode("utf-8-sig")
    return [ln for ln in text.splitlines() if ln.strip()]


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
        json={"code": pcode, "name": "标注项目甲"},
        headers=auth(admin_tok),
    )
    expect(r.status_code == 201, "管理员新建项目", f"{r.status_code} {r.text}")
    pid = body(r).get("id")
    expect(
        _client.post(
            "/api/projects",
            json={"code": pcode, "name": "重复"},
            headers=auth(admin_tok),
        ).status_code
        == 409,
        "重复项目编号被拒(409)",
    )
    expect(
        _client.post(
            "/api/projects",
            json={"code": f"X_{MARK}", "name": "x"},
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
        _client.get("/api/audit-logs", headers=auth(a_tok)).status_code == 403,
        "★ 员工访问审计日志被拒(403)",
    )

    # ★ 行为变更（v2）：看板端点了从 require_manager 改为「登录即可 + 按范围收窄」，
    #   因为菜单表把「数据看板」给了组长，若仍要求 manager，组长点进去会全是 403。
    #   所以这里断言的不再是 403，而是「他拿到的是只有自己的那一份」。
    r = _client.get("/api/stats/overview", headers=auth(a_tok))
    ov_emp = body(r)
    expect(
        r.status_code == 200 and ov_emp.get("scope_label") == "本人",
        "★ 员工能看看板，但范围标签是「本人」",
        f"{r.status_code} {ov_emp.get('scope_label')}",
    )
    # 甲、乙都是 employee，但甲的 scope 只有自己 → 计数必须是 1 而不是 2。
    # 这一条专门盯「scope 漏盖在人员计数上」：那种情况下这里是 2，
    # 而看板上其余数字全都正常，肉眼看不出来。
    expect(
        ov_emp.get("employee_count") == 1,
        "★ 员工看板的人数只有他自己（不含另一位员工）",
        str(ov_emp.get("employee_count")),
    )
    # ★ v2 删掉了 /api/stats/me（「我的统计」页没了）。
    #   删掉而不是留着，是因为它的口径是 v1 的「数量 - 返工量」，
    #   留着就是一段会诱人继续用的死代码。这里断言它**确实**没了。
    expect(
        _client.get("/api/stats/me", headers=auth(a_tok)).status_code == 404,
        "★ /api/stats/me 已删除(404)——不再是 200 的旧口径",
    )

    # ——— 5. 管理者视角 + 审计 ———
    print("\n—— 管理者视角与审计 ——")
    r = _client.get("/api/work-records", headers=auth(admin_tok))
    seen = {x["user_id"] for x in body(r)}
    expect(a_id in seen and b_id in seen, "管理者可见全员数据", str(seen))

    r = _client.get("/api/stats/overview", headers=auth(admin_tok))
    ov = body(r)
    expect(
        r.status_code == 200 and ov.get("scope_label") == "全公司",
        "管理者看板范围是「全公司」",
        f"{r.status_code} {ov.get('scope_label')}",
    )
    # ★ 管理者的员工计数必须 ≥ 2（甲、乙），这条盯的是「scope 对 manager
    #   意外收窄」——那会让超管看到的看板只统计他自己，数字全都偏小，
    #   而所有接口都返回 200。
    expect(
        ov.get("employee_count", 0) >= 2,
        "★ 管理者看板人数含全体员工（scope 没有误伤全量分支）",
        str(ov.get("employee_count")),
    )

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

    # ════════════════════════════════════════════════════════════
    # v2 双轨：团队与角色 / 标注 / 质检 / 隔断 / 导出 / 统计
    # ════════════════════════════════════════════════════════════

    # ——— 6. 团队与角色 ———
    print("\n—— 团队与角色 ——")
    r = _client.post(
        "/api/teams", json={"name": f"甲组_{MARK}"}, headers=auth(admin_tok)
    )
    expect(r.status_code == 201, "管理者新建团队", f"{r.status_code} {r.text}")
    team_a = body(r).get("id")
    expect(
        _client.post(
            "/api/teams", json={"name": f"甲组_{MARK}"}, headers=auth(admin_tok)
        ).status_code
        == 409,
        "同名团队被拒(409)",
    )
    team_b = body(
        _client.post("/api/teams", json={"name": f"乙组_{MARK}"}, headers=auth(admin_tok))
    ).get("id")

    # 夹具：甲乙两组各一个组长 + 组员，外加一个「没挂组的组长」和一个管理者
    la_id = mk_user(f"leaderA_{MARK}", "组长甲", "leader", team_a)
    ea1_id = mk_user(f"empA1_{MARK}", "组员甲一", "employee", team_a)
    ea2_id = mk_user(f"empA2_{MARK}", "组员甲二", "employee", team_a)
    lb_id = mk_user(f"leaderB_{MARK}", "组长乙", "leader", team_b)
    eb1_id = mk_user(f"empB1_{MARK}", "组员乙一", "employee", team_b)
    lx_id = mk_user(f"leaderX_{MARK}", "没组的组长", "leader", None)
    mgr_id = mk_user(f"mgr_{MARK}", "管理者", "manager", None)

    la_tok, ea1_tok = tok(f"leaderA_{MARK}"), tok(f"empA1_{MARK}")
    ea2_tok, lb_tok = tok(f"empA2_{MARK}"), tok(f"leaderB_{MARK}")
    eb1_tok, lx_tok = tok(f"empB1_{MARK}"), tok(f"leaderX_{MARK}")
    mgr_tok = tok(f"mgr_{MARK}")
    expect(all([la_tok, ea1_tok, lb_tok, lx_tok, mgr_tok]), "夹具账号均能登录")

    # 组长必须属于一个团队
    expect(
        _client.patch(
            f"/api/users/{mgr_id}", json={"role": "leader"}, headers=auth(admin_tok)
        ).status_code
        == 422,
        "★ 把没有团队的人设成组长被拒(422)",
    )
    # 一个团队只能有一个组长
    expect(
        _client.patch(
            f"/api/users/{ea2_id}",
            json={"role": "leader", "team_id": team_a},
            headers=auth(admin_tok),
        ).status_code
        == 422,
        "★ 给已有组长的团队再设一个组长被拒(422)",
    )
    # ★ 反向：把在任组长的 team_id 置空也必须被拒——这一条是「先算后写」的试金石，
    #   逐字段校验的写法会放它过去，制造出一个「没挂组的组长」
    expect(
        _client.patch(
            f"/api/users/{la_id}", json={"team_id": None}, headers=auth(admin_tok)
        ).status_code
        == 422,
        "★ 把在任组长移出团队被拒(422)（两个字段必须合起来校验）",
    )
    # 组长不是管理者：管理端点照样 403
    expect(
        _client.get("/api/users", headers=auth(la_tok)).status_code == 403,
        "★ 组长访问账号列表被拒(403)（组长不是小号管理员）",
    )
    expect(
        _client.get("/api/audit-logs", headers=auth(la_tok)).status_code == 403,
        "★ 组长访问审计日志被拒(403)",
    )
    # 组长能拿人员下拉，且**只有本组**
    r = _client.get("/api/users/options", headers=auth(la_tok))
    opts = body(r)
    opt_ids = {o["id"] for o in opts}
    expect(
        r.status_code == 200 and opt_ids == {la_id, ea1_id, ea2_id},
        "★ 组长的人员下拉 = 本组三人（不含别组、不含管理者）",
        str(sorted(opt_ids)),
    )
    # 员工拿到的只有自己
    expect(
        {o["id"] for o in body(_client.get("/api/users/options", headers=auth(ea1_tok)))}
        == {ea1_id},
        "★ 员工的人员下拉只有自己",
    )
    # ★ 质检目标要全员：员工加 ?all=true 也拿得到全公司（已与用户确认）
    r = _client.get("/api/users/options?all=true", headers=auth(ea1_tok))
    all_ids = {o["id"] for o in body(r)}
    expect(
        r.status_code == 200 and {eb1_id, lb_id, ea2_id} <= all_ids,
        "★ ?all=true 时员工也能拿到全员（质检目标下拉用）",
        str(sorted(all_ids)),
    )
    # 停用账号不进下拉（停用的人登不上，给他填数据只会变成谁也看不见的孤儿记录）
    ghost_id = mk_user(f"ghost_{MARK}", "将停用", "employee", team_a)
    expect(
        ghost_id
        in {
            o["id"]
            for o in body(
                _client.get("/api/users/options?all=true", headers=auth(la_tok))
            )
        },
        "（前置）新账号默认出现在全员下拉里",
    )
    _client.patch(
        f"/api/users/{ghost_id}", json={"status": "disabled"}, headers=auth(admin_tok)
    )
    after_ids = {
        o["id"]
        for o in body(_client.get("/api/users/options?all=true", headers=auth(la_tok)))
    }
    expect(
        ghost_id not in after_ids,
        "★ 停用账号从人员下拉消失（?all=true 也挡住了）",
        str(ghost_id in after_ids),
    )
    # 组长的名单里也不能留着他——否则组长会往一个登不上的人头上填数据
    expect(
        ghost_id
        not in {o["id"] for o in body(_client.get("/api/users/options", headers=auth(la_tok)))},
        "★ 停用账号从组长的本组下拉里消失",
    )

    # ——— 7. 标注轨 ———
    print("\n—— 标注轨 ——")
    r = _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today), "item_no": "A-1",
              "box2d": 10, "box3d": 90, "remark": "甲一今天"},
        headers=auth(ea1_tok),
    )
    expect(r.status_code == 201, "登记标注", f"{r.status_code} {r.text}")
    anno1 = body(r)
    expect(anno1.get("box_total") == 100, "工作量 = 2D + 3D (10+90=100)",
           str(anno1.get("box_total")))
    expect(
        anno1.get("suspected_duplicate") is False, "首条不标疑似重复"
    )
    anno1_id = anno1.get("id")

    # ★ 重复**允许**：同人 + 同项目 + 同天 + 同条目号再来一条 → 201 + 提示，不是 409
    r = _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today), "item_no": "A-1",
              "box2d": 5, "box3d": 5},
        headers=auth(ea1_tok),
    )
    expect(
        r.status_code == 201 and body(r).get("suspected_duplicate") is True,
        "★ 重复登记返回 201 + suspected_duplicate=true（不是 409，不拦）",
        f"{r.status_code} {body(r).get('suspected_duplicate')}",
    )
    # 反证：首条现在也变成「疑似重复」了——判定是现算的，不是落库冻结的
    r = _client.get("/api/annotations", headers=auth(ea1_tok))
    first = next(x for x in body(r)["items"] if x["id"] == anno1_id)
    expect(
        first["suspected_duplicate"] is True,
        "★ 疑似重复是现算的：后来补的那条会让先前的首条也标上",
    )
    # ★ 条目号是字符串：`007` 与 `7` 必须是两条独立的记录，不能塌缩
    _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today), "item_no": "007", "box2d": 1},
        headers=auth(ea1_tok),
    )
    r = _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today), "item_no": "7", "box2d": 2},
        headers=auth(ea1_tok),
    )
    expect(
        r.status_code == 201 and body(r).get("suspected_duplicate") is False,
        "★ 条目号 007 与 7 是两条独立记录（存字符串，不塌缩）",
        f"{r.status_code} dup={body(r).get('suspected_duplicate')}",
    )

    # 日期闸门
    expect(
        _client.post(
            "/api/annotations",
            json={"project_id": pid, "work_date": iso(today + timedelta(days=1)),
                  "box2d": 1},
            headers=auth(ea1_tok),
        ).status_code
        == 422,
        "标注：填报未来日期被拒(422)",
    )
    expect(
        _client.post(
            "/api/annotations",
            json={"project_id": pid, "work_date": iso(today - timedelta(days=8)),
                  "box2d": 1},
            headers=auth(ea1_tok),
        ).status_code
        == 422,
        "标注：填报 8 天前被拒(422)",
    )
    r = _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today - timedelta(days=7)),
              "item_no": "old", "box2d": 7},
        headers=auth(ea1_tok),
    )
    expect(r.status_code == 201, "标注：第 7 天(边界)允许", f"{r.status_code} {r.text}")

    # 组员甲二也填一条，供组长范围测试用
    _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today), "item_no": "A-2",
              "box2d": 3, "box3d": 4},
        headers=auth(ea2_tok),
    )
    # 乙组的人各填一条
    _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today), "item_no": "B-1",
              "box2d": 20, "box3d": 30},
        headers=auth(eb1_tok),
    )

    # ——— 8. 质检轨 ———
    print("\n—— 质检轨 ——")
    r = _client.post(
        "/api/qc-records",
        json={"target_user_id": eb1_id, "project_id": pid, "qc_date": iso(today),
              "item_no": "A-1", "result": "pass", "remark": "跨组质检"},
        headers=auth(ea1_tok),
    )
    expect(
        r.status_code == 201,
        "★ 员工可以给**别组**的人登记质检（目标全员可选，已确认）",
        f"{r.status_code} {r.text}",
    )
    xqc_id = body(r).get("id")
    expect(
        body(r).get("inspector_id") == ea1_id,
        "质检记录的作者是登记人自己",
    )
    expect(
        _client.post(
            "/api/qc-records",
            json={"target_user_id": eb1_id, "project_id": pid, "qc_date": iso(today),
                  "item_no": "X", "result": "maybe"},
            headers=auth(ea1_tok),
        ).status_code
        == 422,
        "质检结论拼错('maybe')被拒(422)——Literal 兜住了值域",
    )
    expect(
        _client.post(
            "/api/qc-records",
            json={"target_user_id": ea1_id, "project_id": pid, "qc_date": iso(today),
                  "item_no": "X", "result": "pass"},
            headers=auth(ea1_tok),
        ).status_code
        == 422,
        "不能质检自己(422)",
    )
    expect(
        _client.post(
            "/api/qc-records",
            json={"target_user_id": 999_999_999, "project_id": pid,
                  "qc_date": iso(today), "item_no": "X", "result": "pass"},
            headers=auth(ea1_tok),
        ).status_code
        == 404,
        "质检不存在的目标被拒(404)",
    )

    # 通过率：(project_id, item_no) 分组
    # 先造出 2 通过 + 1 打回 = 3 条 → 0.6667
    _client.post(
        "/api/qc-records",
        json={"target_user_id": ea1_id, "project_id": pid, "qc_date": iso(today),
              "item_no": "PR-1", "result": "pass"},
        headers=auth(eb1_tok),
    )
    _client.post(
        "/api/qc-records",
        json={"target_user_id": ea1_id, "project_id": pid, "qc_date": iso(today),
              "item_no": "PR-1", "result": "pass"},
        headers=auth(eb1_tok),
    )
    _client.post(
        "/api/qc-records",
        json={"target_user_id": ea1_id, "project_id": pid, "qc_date": iso(today),
              "item_no": "PR-1", "result": "reject"},
        headers=auth(eb1_tok),
    )
    r = _client.get(
        f"/api/qc-records/pass-rate?project_id={pid}&item_no=PR-1",
        headers=auth(ea1_tok),
    )
    pr = body(r)
    expect(
        r.status_code == 200 and (pr.get("total"), pr.get("passed"), pr.get("rejected"))
        == (3, 2, 1),
        "通过率分子分母正确(2/3)",
        str(pr),
    )
    expect(pr.get("rate") == 0.6667, "通过率 = 0.6667", str(pr.get("rate")))

    # ★ 跨项目同条目号不互相污染：给项目 B 造一个同名条目号
    pcode_b = f"PRJB_{MARK}"
    pid_b = body(
        _client.post(
            "/api/projects",
            json={"code": pcode_b, "name": "标注项目乙"},
            headers=auth(admin_tok),
        )
    ).get("id")
    _client.post(
        "/api/qc-records",
        json={"target_user_id": ea1_id, "project_id": pid_b, "qc_date": iso(today),
              "item_no": "PR-1", "result": "reject"},
        headers=auth(eb1_tok),
    )
    r = _client.get(
        f"/api/qc-records/pass-rate?project_id={pid}&item_no=PR-1",
        headers=auth(ea1_tok),
    )
    expect(
        (body(r).get("total"), body(r).get("passed")) == (3, 2),
        "★ 项目乙的同名条目号不污染项目甲的通过率（按 project_id + item_no 分组）",
        str(body(r)),
    )
    r = _client.get(
        f"/api/qc-records/pass-rate?project_id={pid_b}&item_no=PR-1",
        headers=auth(ea1_tok),
    )
    expect(
        (body(r).get("total"), body(r).get("passed")) == (1, 0),
        "★ 项目乙自己算自己的（1 条，全打回）",
        str(body(r)),
    )
    # 空表单 → 0.0 而不是 None / NaN
    r = _client.get(
        f"/api/qc-records/pass-rate?project_id={pid}&item_no=NOBODY",
        headers=auth(ea1_tok),
    )
    expect(
        r.status_code == 200 and body(r).get("rate") == 0.0
        and body(r).get("total") == 0,
        "★ 没有任何历史的条目号返回 rate=0.0（不是 None，也不是 500）",
        f"{r.status_code} {r.text}",
    )
    expect(
        _client.get("/api/qc-records/pass-rate", headers=auth(ea1_tok)).status_code
        == 200,
        "表单没填全时通过率接口也返回 200（前端可以无条件调用）",
    )

    # ——— 9. ★ 隔断（v2 核心）———
    print("\n—— ★ 隔断（v2）——")

    # 员工：只看到自己
    r = _client.get("/api/annotations", headers=auth(ea1_tok))
    rows = body(r)["items"]
    expect(
        all(x["user_id"] == ea1_id for x in rows) and len(rows) >= 4,
        "★ 员工标注列表只含自己的记录",
        str({x["user_id"] for x in rows}),
    )
    r = _client.get(f"/api/annotations?user_id={ea2_id}", headers=auth(ea1_tok))
    expect(
        body(r)["total"] == 0,
        "★ 员工传 user_id=同组同事 → 空列表（scope 只能收窄，不可能放大）",
        str(body(r)["total"]),
    )
    # 改别人的记录 → 404，且与「不存在」的 404 逐字相同
    with SessionLocal() as db:
        ea2_rec = (
            db.query(AnnotationRecord)
            .filter(AnnotationRecord.user_id == ea2_id)
            .order_by(AnnotationRecord.id.desc())
            .first()
        )
        ea2_rec_id = ea2_rec.id if ea2_rec else -1
    d_other = body(
        _client.patch(
            f"/api/annotations/{ea2_rec_id}", json={"box2d": 1}, headers=auth(ea1_tok)
        )
    ).get("detail")
    d_missing = body(
        _client.patch(
            "/api/annotations/999999999", json={"box2d": 1}, headers=auth(ea1_tok)
        )
    ).get("detail")
    r_other = _client.patch(
        f"/api/annotations/{ea2_rec_id}", json={"box2d": 1}, headers=auth(ea1_tok)
    )
    expect(
        r_other.status_code == 404, "★ 员工改他人记录返回 404", str(r_other.status_code)
    )
    expect(
        d_other == d_missing == "记录不存在",
        "★ 「越权」与「不存在」的 detail 逐字相同（挡住存在性预言机）",
        f"越权={d_other!r} 不存在={d_missing!r}",
    )
    expect(
        _client.delete(f"/api/annotations/{ea2_rec_id}", headers=auth(ea1_tok)).status_code
        == 404,
        "★ 员工删他人记录返回 404",
    )

    # 组长：看到本组三人，看不到别组
    r = _client.get("/api/annotations", headers=auth(la_tok))
    seen = {x["user_id"] for x in body(r)["items"]}
    # 本组四个人（组长甲、甲一、甲二、ghost），但只有**有记录**的人会出现在列表里：
    # 组长甲自己没填过，ghost 已停用且没填过 —— 所以是 {甲一, 甲二}。
    # ★ 这里刻意不断言「含他自己」：名册成员与「有数据的人」是两回事，
    #   拿成员集合去比列表 user_id 集合，会把「谁填过」和「谁在这个组」混为一谈。
    expect(
        seen == {ea1_id, ea2_id},
        "★ 组长标注列表 = 本组**有记录**的人（别组的看不到）",
        str(sorted(seen)),
    )
    expect(
        body(_client.get(f"/api/annotations?user_id={eb1_id}", headers=auth(la_tok)))[
            "total"
        ]
        == 0,
        "★ 组长传别组组员的 user_id → 空列表（不报错也不泄露）",
    )
    r = _client.get(f"/api/annotations?user_id={ea1_id}", headers=auth(la_tok))
    expect(
        body(r)["total"] > 0 and all(x["user_id"] == ea1_id for x in body(r)["items"]),
        "★ 组长传本组组员的 user_id → 正常收窄到那一个人",
    )

    # 组长改本组组员 → 200 + 留痕；改别组 → 404
    r = _client.patch(
        f"/api/annotations/{anno1_id}", json={"box2d": 11}, headers=auth(la_tok)
    )
    expect(
        r.status_code == 200 and body(r).get("edited_by_manager") is True,
        "★ 组长改本组组员记录 → 200 且带 edited_by_manager 标记",
        f"{r.status_code} {body(r).get('edited_by_manager')}",
    )
    with SessionLocal() as db:
        eb1_rec = (
            db.query(AnnotationRecord)
            .filter(AnnotationRecord.user_id == eb1_id)
            .order_by(AnnotationRecord.id.desc())
            .first()
        )
        eb1_rec_id = eb1_rec.id if eb1_rec else -1
    expect(
        _client.patch(
            f"/api/annotations/{eb1_rec_id}", json={"box2d": 1}, headers=auth(la_tok)
        ).status_code
        == 404,
        "★ 组长改别组组员的记录 → 404",
    )

    # ★ 组长可改组员 100 天前的记录（7 天窗口对组长豁免）
    #   ★ 这条记录必须**挂在甲一名下**（`user_id=ea1_id`），不是管理者自己名下。
    #     不写 user_id 的话它归管理者，组长改它照样 404——断言会红，但红的是
    #     「组长越权被挡住」，看起来像权限做对了，实际是夹具挂错了人。
    #     管理者代填到甲一头上，顺带也验了「管理者豁免 7 天窗口」：
    #     v1 的「新建」路径是不豁免的，这是本版有意放宽的一处，见 core/rules.py。
    r = _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today - timedelta(days=100)),
              "item_no": "ancient", "box2d": 50, "user_id": ea1_id},
        headers=auth(mgr_tok),
    )
    expect(
        r.status_code == 201 and body(r).get("user_id") == ea1_id,
        "★ 管理者可代填 100 天前的记录（豁免 7 天窗口）",
        f"{r.status_code} {r.text}",
    )
    ancient_id = body(r).get("id")
    r = _client.patch(
        f"/api/annotations/{ancient_id}", json={"box2d": 51}, headers=auth(la_tok)
    )
    expect(
        r.status_code == 200,
        "★ 组长可改组员 100 天前的记录（7 天窗口对组长豁免）",
        f"{r.status_code} {r.text}",
    )
    # 反证：员工改自己 100 天前的记录仍然被拦（窗口没被一豁免全放掉）
    # 先得有一条他自己的老记录 —— 上面那条是代填到别人名下的，用不上。
    with SessionLocal() as db:
        old = AnnotationRecord(
            user_id=ea1_id, project_id=pid,
            work_date=today - timedelta(days=100), item_no="self_ancient",
            box2d=1, box3d=0,
        )
        db.add(old)
        db.commit()
        old_id = old.id
    expect(
        _client.patch(
            f"/api/annotations/{old_id}", json={"box2d": 2}, headers=auth(ea1_tok)
        ).status_code
        == 422,
        "★ 员工改自己 100 天前的记录仍被拒(422)——豁免只给了组长/管理者",
    )

    # ★ 跨组质检的可见性：两个方向都要能看见
    r = _client.get("/api/qc-records", headers=auth(ea1_tok))
    got = {x["id"]: x for x in body(r)["items"]}
    expect(
        xqc_id in got,
        "★ 质检员看得见自己**跨组**提交的那条（否则系统在否认他的提交）",
        str(sorted(got)),
    )
    expect(
        got.get(xqc_id, {}).get("mine") is True,
        "跨组那条对登记人标 mine=true",
    )
    r = _client.get("/api/qc-records", headers=auth(lb_tok))
    lb_ids = {x["id"] for x in body(r)["items"]}
    expect(
        xqc_id in lb_ids,
        "★ 被质检人的组长也看得见同一条（target 口径）",
        str(sorted(lb_ids)),
    )
    # 无关员工（甲二）看不到那条跨组质检：他既不是登记人，也不是目标
    r = _client.get("/api/qc-records", headers=auth(ea2_tok))
    expect(
        xqc_id not in {x["id"] for x in body(r)["items"]},
        "★ 无关员工看不到别人之间的质检记录",
    )
    # 而甲二能看到别人质检**他**的记录
    _client.post(
        "/api/qc-records",
        json={"target_user_id": ea2_id, "project_id": pid, "qc_date": iso(today),
              "item_no": "A-2", "result": "reject"},
        headers=auth(la_tok),
    )
    r = _client.get("/api/qc-records", headers=auth(ea2_tok))
    tgt_rows = [x for x in body(r)["items"] if x["target_user_id"] == ea2_id]
    expect(
        len(tgt_rows) >= 1 and all(x["mine"] is False for x in tgt_rows),
        "★ 被质检人能看见质检自己的记录，且标 mine=false（不是他提交的）",
    )

    # ★★ 组长给自己组员录一条质检**再编辑它** → **不应**出现「被管理者修改」标记。
    #    这一条盯的是「留痕判定用了 target_user_id 而不是 inspector_id」那个 bug。
    #    它只在「组长兼任质检员」时现形，是最容易漏测的组合。
    r = _client.post(
        "/api/qc-records",
        json={"target_user_id": ea1_id, "project_id": pid, "qc_date": iso(today),
              "item_no": "SELF-QC", "result": "pass"},
        headers=auth(la_tok),
    )
    self_qc_id = body(r).get("id")
    r = _client.patch(
        f"/api/qc-records/{self_qc_id}", json={"remark": "改一下备注"},
        headers=auth(la_tok),
    )
    expect(
        r.status_code == 200 and body(r).get("edited_by_manager") is False,
        "★★ 组长改自己录的质检不留痕（留痕判定必须用 inspector_id 而非 target_user_id）",
        f"{r.status_code} edited_by_manager={body(r).get('edited_by_manager')}",
    )
    # 对照一：组长改**别人**录的、且目标也不在他组里的质检 → 404
    r = _client.patch(
        f"/api/qc-records/{xqc_id}", json={"remark": "组长改的"},
        headers=auth(la_tok),
    )
    expect(
        r.status_code == 404,
        "★ 组长改别人录的、目标也不在本组的质检 → 404（并集的两个分支都不成立）",
        str(r.status_code),
    )
    # 对照二：组长改**别人**录的、目标在本组的质检 → 200 且留痕
    peer_qc_id = body(
        _client.post(
            "/api/qc-records",
            json={"target_user_id": ea2_id, "project_id": pid, "qc_date": iso(today),
                  "item_no": "PEER-QC", "result": "pass"},
            headers=auth(ea1_tok),
        )
    ).get("id")
    r = _client.patch(
        f"/api/qc-records/{peer_qc_id}", json={"remark": "属下改"}, headers=auth(la_tok)
    )
    expect(
        r.status_code == 200 and body(r).get("edited_by_manager") is True,
        "★ 组长改别人录的、目标在本组的质检 → 留痕（mine 判定看的是 inspector）",
        f"{r.status_code} {body(r).get('edited_by_manager')}",
    )
    expect(
        body(r).get("inspector_name") == "组员甲一",
        "留痕的那条作者没被改写（改的是记录，不是归属）",
        str(body(r).get("inspector_name")),
    )

    # 代填归属
    expect(
        _client.post(
            "/api/annotations",
            json={"project_id": pid, "work_date": iso(today - timedelta(days=2)),
                  "item_no": "forge", "box2d": 1, "user_id": ea2_id},
            headers=auth(ea1_tok),
        ).status_code
        == 404,
        "★ 员工代填给同组同事 → 404（v1 是静默忽略，v2 改判 404）",
    )
    r = _client.post(
        "/api/annotations",
        json={"project_id": pid, "work_date": iso(today - timedelta(days=2)),
              "item_no": "onbehalf", "box2d": 60, "user_id": ea1_id},
        headers=auth(la_tok),
    )
    expect(
        r.status_code == 201 and body(r).get("user_id") == ea1_id
        and body(r).get("edited_by_manager") is True,
        "★ 组长代填给本组组员 → 201 归组员 + 留痕",
        f"{r.status_code} {body(r)}",
    )
    expect(
        _client.post(
            "/api/annotations",
            json={"project_id": pid, "work_date": iso(today - timedelta(days=2)),
                  "item_no": "cross", "box2d": 1, "user_id": eb1_id},
            headers=auth(la_tok),
        ).status_code
        == 404,
        "★ 组长代填给别组组员 → 404",
    )
    # 反证：那次越权代填没有静默落到组长自己头上
    with SessionLocal() as db:
        n = (
            db.query(AnnotationRecord)
            .filter(AnnotationRecord.user_id == la_id,
                    AnnotationRecord.item_no == "cross")
            .count()
        )
    expect(n == 0, "★ 越权代填没有静默落到组长自己名下（v1 的真实 bug）", str(n))

    # 配置边界：没挂组的组长 = 空集
    r = _client.get("/api/annotations", headers=auth(lx_tok))
    expect(
        r.status_code == 200 and body(r)["total"] == 0,
        "★ 没挂组的组长标注列表为空集（绝不退化成全量）",
        f"{r.status_code} total={body(r)['total']}",
    )
    expect(
        _client.get("/api/qc-records", headers=auth(lx_tok)).status_code == 200
        and body(_client.get("/api/qc-records", headers=auth(lx_tok)))["total"] == 0,
        "★ 没挂组的组长质检列表同样是空集",
    )
    #    ★ 空集只吃掉「别人的记录」这一条路径；他自己那条走 `owner_id == user.id`
    #      的早退分支，跟 scope 无关，所以仍然能改。这条要一起钉住——
    #      否则将来有人「顺手」把 self 早退挪到 scope 检查之后，
    #      这个组长会连自己的记录都改不了，而没有任何断言会红。
    lx_own_id = body(
        _client.post(
            "/api/annotations",
            json={"project_id": pid, "work_date": iso(today), "item_no": "LX-OWN",
                  "box2d": 4, "box3d": 6},
            headers=auth(lx_tok),
        )
    ).get("id")
    expect(
        _client.patch(
            f"/api/annotations/{lx_own_id}", json={"box2d": 5}, headers=auth(lx_tok)
        ).status_code
        == 200,
        "★ 没挂组的组长仍能改**自己**的记录（self 分支与 scope 无关）",
    )
    expect(
        _client.patch(
            f"/api/annotations/{anno1_id}", json={"box2d": 9}, headers=auth(lx_tok)
        ).status_code
        == 404,
        "★ 没挂组的组长改他人记录 → 404（空集，不是「404 或 403」）",
    )

    # ——— 10. 管理者 ———
    print("\n—— 管理者 ———")
    r = _client.get("/api/annotations", headers=auth(admin_tok))
    seen = {x["user_id"] for x in body(r)["items"]}
    expect(
        {ea1_id, ea2_id, eb1_id} <= seen,
        "管理者可见全员标注记录",
        str(sorted(seen)),
    )
    r = _client.get("/api/teams", headers=auth(admin_tok))
    teams = {t["id"]: t for t in body(r)}
    expect(
        # 4 = 组长甲 + 甲一 + 甲二 + 上面那个已停用的 ghost。
        # ★ 停用的人仍然计入成员数：他是这个组的人，只是不能登录了。
        #   成员数若排掉停用账号，组长看到的「本组 3 人」与实际的组员名单
        #   就对不上，而两者都不报错。停用与「不在这个组」是两回事。
        teams.get(team_a, {}).get("member_count") == 4
        and teams.get(team_a, {}).get("leader_name") == "组长甲",
        "团队列表带成员数（含停用）与派生的组长名",
        str(teams.get(team_a)),
    )
    expect(
        _client.delete(f"/api/teams/{team_a}", headers=auth(admin_tok)).status_code == 422,
        "★ 有成员的团队不能删(422)",
    )
    # ★ 新守卫：有标注/质检记录的账号和项目都删不掉
    expect(
        _client.delete(f"/api/users/{ea1_id}", headers=auth(admin_tok)).status_code == 422,
        "★ 有标注记录的账号不能删(422)——新守卫（旧守卫只查 v1 表，会「删除成功」）",
    )
    expect(
        _client.delete(f"/api/users/{eb1_id}", headers=auth(admin_tok)).status_code == 422,
        "★ 只有质检记录的账号也不能删（质检表两列都要查）",
    )
    expect(
        _client.delete(f"/api/projects/{pid}", headers=auth(admin_tok)).status_code == 422,
        "★ 有标注记录的项目不能删(422)",
    )
    expect(
        _client.delete(f"/api/projects/{pid_b}", headers=auth(admin_tok)).status_code == 422,
        "★ 只有质检记录的项目也不能删(422)",
    )
    # 一条记录都没有的账号/项目仍然可以删（守卫不能把正常功能也锁死）
    spare_id = mk_user(f"spare_{MARK}", "闲人", "employee", None)
    expect(
        _client.delete(f"/api/users/{spare_id}", headers=auth(admin_tok)).status_code == 200,
        "没记录的账号仍可正常删除（守卫没有误伤）",
    )
    spare_pid = body(
        _client.post(
            "/api/projects", json={"code": f"SPARE_{MARK}", "name": "空项目"},
            headers=auth(admin_tok),
        )
    ).get("id")
    expect(
        _client.delete(f"/api/projects/{spare_pid}", headers=auth(admin_tok)).status_code
        == 200,
        "没记录的项目仍可正常删除（守卫没有误伤）",
    )
    # 空的团队可以删
    empty_team = body(
        _client.post("/api/teams", json={"name": f"空组_{MARK}"}, headers=auth(admin_tok))
    ).get("id")
    expect(
        _client.delete(f"/api/teams/{empty_team}", headers=auth(admin_tok)).status_code
        == 200,
        "空团队可以删",
    )

    # ——— 11. 导出 ———
    print("\n—— 导出 ——")
    r = _client.get("/api/annotations/export", headers=auth(ea1_tok))
    expect(r.status_code == 200, "员工导出标注 CSV", f"{r.status_code} {r.text[:200]}")
    lines = csv_rows(r)
    expect(
        r.content.startswith(b"\xef\xbb\xbf"),
        "★ CSV 以 UTF-8 BOM 开头（否则 Excel 打开中文全是乱码）",
        str(r.content[:6]),
    )
    cd = r.headers.get("content-disposition", "")
    expect(
        "filename=" in cd and "filename*=UTF-8''" in cd,
        "★ Content-Disposition 同时给了 ASCII 兜底名和 UTF-8 名",
        cd,
    )
    # 导出行数 == 同参数列表的 total（防「导出和列表对不上」）
    total_ea1 = body(_client.get("/api/annotations", headers=auth(ea1_tok)))["total"]
    expect(
        len(lines) - 1 == total_ea1,
        "★ 员工导出行数 == 同参数 list 的 total",
        f"csv={len(lines) - 1} list={total_ea1}",
    )
    r = _client.get("/api/annotations/export", headers=auth(la_tok))
    total_la = body(_client.get("/api/annotations", headers=auth(la_tok)))["total"]
    expect(
        len(csv_rows(r)) - 1 == total_la,
        "★ 组长导出行数 == 同参数 list 的 total",
        f"csv={len(csv_rows(r)) - 1} list={total_la}",
    )
    expect(
        total_la > total_ea1,
        "★ 组长导出比员工多（确实按范围放开，不是恰好相等）",
        f"组长={total_la} 员工={total_ea1}",
    )
    # 范围外的 user_id → 只有表头
    r = _client.get(f"/api/annotations/export?user_id={eb1_id}", headers=auth(la_tok))
    expect(
        len(csv_rows(r)) == 1,
        "★ 导出传范围外的 user_id → 只剩表头（导出与列表同一段筛选代码）",
        str(csv_rows(r)),
    )
    # 质检轨导出
    r = _client.get("/api/qc-records/export", headers=auth(ea1_tok))
    total_qc_ea1 = body(_client.get("/api/qc-records", headers=auth(ea1_tok)))["total"]
    expect(
        r.status_code == 200 and len(csv_rows(r)) - 1 == total_qc_ea1,
        "★ 质检导出行数 == 同参数 list 的 total",
        f"{r.status_code} csv={len(csv_rows(r)) - 1} list={total_qc_ea1}",
    )
    # ★ 超限 422（把上限临时压到 1 行来验，不真造五万行）
    from app.services import export as export_mod

    saved = export_mod.EXPORT_MAX_ROWS
    export_mod.EXPORT_MAX_ROWS = 1
    try:
        r = _client.get("/api/annotations/export", headers=auth(la_tok))
        expect(
            r.status_code == 422 and "超过" in body(r).get("detail", ""),
            "★ 导出超行数上限 → 422 提示缩小范围（不静默截断）",
            f"{r.status_code} {r.text[:120]}",
        )
    finally:
        export_mod.EXPORT_MAX_ROWS = saved
    expect(
        _client.get("/api/annotations/export", headers=auth(la_tok)).status_code == 200,
        "恢复上限后导出恢复正常",
    )

    # ——— 12. 统计 ———
    print("\n—— 统计 ——")
    r = _client.get("/api/stats/overview", headers=auth(admin_tok))
    ov = body(r)
    expect(
        ov.get("total_box") == ov.get("total_box2d", 0) + ov.get("total_box3d", 0),
        "★ total_box == box2d + box3d",
        str(ov),
    )
    expect(
        ov.get("qc_total") == ov.get("qc_pass", 0) + ov.get("qc_reject", 0),
        "★ qc_total == qc_pass + qc_reject",
        str(ov),
    )
    expect(
        "total_rework" not in ov and "total_amount" not in ov and "pass_rate" not in ov,
        "★ v1 的同名不同义字段（total_rework/total_amount/pass_rate）已彻底删除",
        str(sorted(ov)),
    )
    expect(
        ov.get("qc_pass_rate") == round(ov.get("qc_pass", 0) / ov.get("qc_total", 1), 4),
        "qc_pass_rate 与分子分母自洽",
        str(ov.get("qc_pass_rate")),
    )
    # 看板与列表的口径必须一致。
    # ★ 概览默认是**最近 30 天**，而标注列表默认**不带日期**（全时段）。
    #   直接拿两者比会红——而红的原因是两个接口的默认窗口不同，不是口径错。
    #   夹具里确实有 100 天前的记录，所以这里必须显式给概览一个覆盖全段的窗口，
    #   让「窗口」这个变量被消掉，只剩「口径」这一个变量。
    wide = (
        f"date_from={iso(today - timedelta(days=400))}&date_to={iso(today)}"
    )
    ov = body(_client.get(f"/api/stats/overview?{wide}", headers=auth(admin_tok)))
    anno_total_all = body(_client.get("/api/annotations", headers=auth(admin_tok)))[
        "total"
    ]
    expect(
        ov.get("annotation_count") == anno_total_all,
        "★ 看板的标注条数 == 列表 total（同一段 scope，同一个时间窗口）",
        f"看板={ov.get('annotation_count')} 列表={anno_total_all}",
    )
    qc_total_all = body(_client.get("/api/qc-records", headers=auth(admin_tok)))["total"]
    expect(
        ov.get("qc_total") == qc_total_all,
        "★ 看板的质检条数 == 质检列表 total",
        f"看板={ov.get('qc_total')} 列表={qc_total_all}",
    )

    # trend 补零
    r = _client.get("/api/stats/trend?days=14", headers=auth(admin_tok))
    pts = body(r).get("points", [])
    expect(
        len(pts) == 14,
        "★ trend 补零点数 == 请求天数（否则前端折线会断线）",
        str(len(pts)),
    )
    expect(
        all(
            p["box_total"] == p["box2d"] + p["box3d"]
            and p["qc_total"] == p["qc_pass"] + p["qc_reject"]
            for p in pts
        ),
        "trend 每一天内部自洽",
    )
    expect(
        body(r).get("total_box") == sum(p["box_total"] for p in pts)
        and body(r).get("qc_total") == sum(p["qc_total"] for p in pts),
        "trend 合计 == 各天之和",
    )

    # by-user：两个方向的通过率不能互换
    r = _client.get("/api/stats/by-user", headers=auth(admin_tok))
    ub_rows = {x["user_id"]: x for x in body(r)}
    ea1_row = ub_rows.get(ea1_id, {})
    eb1_row = ub_rows.get(eb1_id, {})
    # 甲一：做质检 1 条(pass) ；被质检 4 条(3 pass 1 reject)
    expect(
        # 甲一做质检 2 条：跨组检乙一(通过) + 检本组甲二(通过)
        ea1_row.get("qc_as_inspector_total") == 2
        and ea1_row.get("qc_as_inspector_pass") == 2,
        "★ by-user 的「他做质检」口径正确",
        str(ea1_row),
    )
    expect(
        # 甲一被质检 5 条：项目甲 PR-1 三条(2 过 1 打回) + 项目乙 PR-1 一条(打回)
        #                  + 组长给他录的 SELF-QC 一条(过)
        # ★ 5 条里有 2 条来自**项目乙**——它们必须在分子分母里都算上，
        #   否则「他被检的通过率」就不是他真实的通过率。
        ea1_row.get("qc_as_target_total") == 5
        and ea1_row.get("qc_as_target_pass") == 3,
        "★ by-user 的「他被质检」口径正确",
        str({k: ea1_row.get(k) for k in ("qc_as_target_total", "qc_as_target_pass")}),
    )
    expect(
        ea1_row.get("qc_as_inspector_pass_rate") == 1.0
        and ea1_row.get("qc_as_target_pass_rate") == 0.6,
        "★ 两个方向的通过率是不同的两个数（方向没有互换）",
        f"他检={ea1_row.get('qc_as_inspector_pass_rate')} "
        f"被检={ea1_row.get('qc_as_target_pass_rate')}",
    )
    expect(
        eb1_row.get("qc_as_inspector_total", 0) >= 4
        and eb1_row.get("qc_as_target_total") == 1,
        "★ 乙组组员的方向与甲一相反（做质检 4 条 / 被质检 1 条）",
        str({k: eb1_row.get(k) for k in
             ("qc_as_inspector_total", "qc_as_target_total")}),
    )
    expect(
        ea1_row.get("box_total") == ea1_row.get("box2d", 0) + ea1_row.get("box3d", 0),
        "by-user 的 box_total 自洽",
    )

    # by-project
    r = _client.get("/api/stats/by-project", headers=auth(admin_tok))
    pb = {x["project_id"]: x for x in body(r)}
    expect(
        pb.get(pid, {}).get("qc_total", 0) >= 4
        and pb.get(pid, {}).get("qc_pass", 0) >= 2,
        "by-project 带质检两向指标",
        str(pb.get(pid)),
    )
    expect(
        pb.get(pid_b, {}).get("box_total") == 0
        and pb.get(pid_b, {}).get("qc_total") == 1,
        "只有质检记录的项目也出现在 by-project 里",
        str(pb.get(pid_b)),
    )

    # 记录页顶部的卡片
    r = _client.get("/api/stats/annotation-summary", headers=auth(ea1_tok))
    summ = body(r)
    expect(
        r.status_code == 200 and summ.get("today_box", 0) >= 100
        and summ.get("scope_label") == "本人",
        "标注统计卡：员工拿到自己的今日工作量",
        str(summ),
    )
    with SessionLocal() as db:
        expect_db_today = (
            db.query(func.coalesce(func.sum(AnnotationRecord.box2d + AnnotationRecord.box3d), 0))
            .filter(AnnotationRecord.user_id == ea1_id,
                    AnnotationRecord.work_date == today_cn())
            .scalar()
        )
    expect(
        summ.get("today_box") == int(expect_db_today),
        "★ 统计卡的「今日」用的是 today_cn()，与库里当天数据对得上",
        f"卡片={summ.get('today_box')} 直查={int(expect_db_today)}",
    )
    r = _client.get("/api/stats/qc-summary", headers=auth(ea1_tok))
    qs = body(r)
    expect(
        r.status_code == 200
        and qs.get("total") == qs.get("passed", 0) + qs.get("rejected", 0),
        "质检统计卡自洽",
        str(qs),
    )
    expect(
        body(_client.get("/api/stats/qc-summary", headers=auth(admin_tok))).get("total")
        == qc_total_all,
        "★ 质检卡片 total == 质检列表 total（同一个可见性谓词）",
    )
    # 组长卡片 = 本组口径，且与他的列表一致
    r = _client.get("/api/stats/annotation-summary", headers=auth(la_tok))
    expect(
        body(r).get("scope_label") == "本组全量"
        and body(r).get("total_box") == sum(
            x["box_total"]
            for x in body(_client.get("/api/annotations?limit=2000", headers=auth(la_tok)))[
                "items"
            ]
        ),
        "★ 组长的卡片是「本组全量」，且与他的列表逐条对得上",
        str(body(r)),
    )

    # ——— 13. 停用即时失效 ———
    print("\n—— 账号停用 ——")
    r = _client.patch(
        f"/api/users/{a_id}", json={"status": "disabled"}, headers=auth(admin_tok)
    )
    expect(r.status_code == 200, "管理员停用员工甲", f"{r.status_code} {r.text}")
    # 换一个仍然存在、且需要登录的端点来验「旧 token 立即失效」。
    # （原来用的是 /api/stats/me，v2 删掉了它，用不存在的端点会拿到 404 而不是 403，
    #   那样这条断言会「通过」但什么都没验到——最容易蒙混过关的一种假绿。）
    expect(
        _client.get("/api/annotations", headers=auth(a_tok)).status_code == 403,
        "★ 停用后旧 token 立即失效(403)",
    )
    expect(
        _client.patch(
            f"/api/users/{a_id}", json={"status": "active"}, headers=auth(admin_tok)
        ).status_code
        == 200,
        "可重新启用",
    )

    # ——— 14. 注册限流 ———
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
        tids = [
            t.id for t in db.query(Team).filter(Team.name.like(f"%{MARK}")).all()
        ]
        rids = (
            [r.id for r in db.query(WorkRecord).filter(WorkRecord.user_id.in_(uids)).all()]
            if uids
            else []
        )
        # v2 两张新表的记录：★ 漏掉它们的话，第二次跑同一脚本时
        # 「组长的列表是空集」这类断言会拿到上一轮的残留而变红，
        # 而且红在一个完全无关的位置——夹具污染比不清理更难查。
        arids = (
            [r.id for r in db.query(AnnotationRecord)
             .filter(AnnotationRecord.user_id.in_(uids)).all()]
            if uids
            else []
        )
        qrids = (
            [r.id for r in db.query(QcRecord)
             .filter(QcRecord.inspector_id.in_(uids)).all()]
            + [r.id for r in db.query(QcRecord)
               .filter(QcRecord.target_user_id.in_(uids)).all()]
            if uids
            else []
        )
        qrids = sorted(set(qrids))

        pairs = (
            [("work_record", str(i)) for i in rids]
            + [("annotation", str(i)) for i in arids]
            + [("qc_record", str(i)) for i in qrids]
            + [("user", str(i)) for i in uids]
            + [("project", str(i)) for i in pids]
            + [("team", str(i)) for i in tids]
        )
        if pairs:
            db.query(AuditLog).filter(
                tuple_(AuditLog.target_type, AuditLog.target_id).in_(pairs)
            ).delete(synchronize_session=False)
        if uids:
            # 员工本人当 actor 的日志（创建团队是管理者操作的，上面按 target 那一遍兜）
            db.query(AuditLog).filter(AuditLog.actor_id.in_(uids)).delete(
                synchronize_session=False
            )
        # —— 先删挂在人与项目上的记录，再删人、项目、团队 ——
        for model, col, ids in (
            (WorkRecord, WorkRecord.id, rids),
            (AnnotationRecord, AnnotationRecord.id, arids),
            (QcRecord, QcRecord.id, qrids),
        ):
            if ids:
                db.query(model).filter(col.in_(ids)).delete(synchronize_session=False)
        # 组员是刚才那批人；先把他们移出团队再删人，否则删不掉……
        # 其实 model 上没有外键，但「先解散再删人」保证中途任何一步失败都不留半截状态。
        if tids:
            db.query(User).filter(User.team_id.in_(tids)).update(
                {"team_id": None}, synchronize_session=False
            )
        if uids:
            db.query(User).filter(User.id.in_(uids)).delete(synchronize_session=False)
        db.query(Project).filter(Project.id.in_(pids or [-1])).delete(
            synchronize_session=False
        )
        if tids:
            db.query(Team).filter(Team.id.in_(tids)).delete(synchronize_session=False)
        db.commit()

        left = {
            "users": db.query(User).filter(User.username.like(f"%{MARK}")).count(),
            "projects": db.query(Project).filter(Project.code.like(f"%{MARK}")).count(),
            "teams": db.query(Team).filter(Team.name.like(f"%{MARK}")).count(),
            "v1记录": db.query(WorkRecord).filter(WorkRecord.id.in_(rids or [-1])).count(),
            "标注": db.query(AnnotationRecord)
            .filter(AnnotationRecord.id.in_(arids or [-1])).count(),
            "质检": db.query(QcRecord).filter(QcRecord.id.in_(qrids or [-1])).count(),
        }
    expect(
        all(v == 0 for v in left.values()),
        "测试数据已清理干净（含 v2 的标注/质检/团队）",
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
