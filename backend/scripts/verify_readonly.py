"""只读演示账号回归：写被拦、读放行、不误伤正常账号。

用法（backend 目录下）：
    .venv/Scripts/python.exe scripts/verify_readonly.py
    DATABASE_URL=sqlite:///./_ro.db .venv/Scripts/python.exe scripts/verify_readonly.py

————————————————————————————————————————————————————————————
为什么这个脚本必须存在

赛事/评审要登录线上环境参观，所以线上有一个只读演示账号。这个账号一旦能写，
评委（或任何拿到密码的人）就能改真实的生产数据——而密码就印在公开仓库的
README 和 PPT 上。所以「只读」不是用户体验，是**安全边界**，必须有回归。

三条断言各自挡一种走法：

  1. 写被拦  —— 挂漏一个 router 就是一处口子。注意 `main.py` 是本项目唯一
     的挂载点，所以这里**逐个 router 各打一发**，而不是只测 teams 一个。
  2. 读放行  —— 拦过头会让演示变成「什么都打不开」，等同于没做。
  3. 不误伤  —— 守卫是按 request.method 判的，最容易出的错是写成「所有
     非 GET 都拦」，那会把正常账号一起打死。所以同一批发请求要用**普通
     账号再打一遍**，断言它拿到的**不是 403**。

另外单独验「登录接口没被守卫误伤」：`/api/auth` 是整个 main.py 里唯一
没挂守卫的路由组（它的 POST /login、/register 是公开接口）。挂错的直接
后果就是所有人登不进来。

夹具刻意用 **super_admin** 而不是低权限角色：超管是权限最高的角色，写操作
本来百分之百能过。这样「403」就只能来自只读标记本身，不可能是权限不够，
变量被隔离干净了。
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401  确保模型注册
from app.core.security import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.team import Team  # noqa: E402
from app.models.user import User  # noqa: E402

PASS, FAIL = 0, []
_client = TestClient(app)
SUF = str(int(time.time()))[-6:]
MARK = f"ro{SUF}"
PWD = "pass1234"

# 与 core/deps.py 的 reject_readonly_write 逐字一致
DETAIL = "当前为只读演示账号，不能修改数据"


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


def mk_user(username: str, name: str, role: str, readonly: bool) -> int:
    with SessionLocal() as db:
        u = User(
            username=username,
            name=name,
            password_hash=hash_password(PWD),
            role=role,
            status="active",
            is_readonly=readonly,
        )
        db.add(u)
        db.commit()
        return u.id


def tok(username: str) -> str:
    r = _client.post("/api/auth/login", json={"username": username, "password": PWD})
    return body(r).get("access_token", "")


def main() -> int:
    Base.metadata.create_all(engine)
    print(f"=== 目标库：{'sqlite(冒烟)' if engine.dialect.name == 'sqlite' else 'PostgreSQL'}"
          f" | 标记 {MARK} ===\n")

    ro_id = mk_user(f"{MARK}_ro", f"{MARK}-只读", "super_admin", True)
    rw_id = mk_user(f"{MARK}_rw", f"{MARK}-正常", "super_admin", False)
    with SessionLocal() as db:
        db.add(Team(name=f"{MARK}-甲组"))
        db.commit()

    # ————————————————————————————————————————————
    # 1) 登录接口没被守卫误伤（/api/auth 是唯一豁免的路由组）
    # ————————————————————————————————————————————
    print("—— 登录——")
    ro_tok, rw_tok = tok(f"{MARK}_ro"), tok(f"{MARK}_rw")
    expect(bool(ro_tok), "★ 只读账号仍能登录（/api/auth 未被守卫误伤）")
    expect(bool(rw_tok), "普通账号能登录")
    if not (ro_tok and rw_tok):
        print("\n登录就失败了，后面全都没意义，提前退出。")
        return 1
    ROH, RWH = auth(ro_tok), auth(rw_tok)

    # ————————————————————————————————————————————
    # 2) /auth/me 把只读标记带给前端
    # ————————————————————————————————————————————
    print("\n—— /auth/me ——")
    me_ro = body(_client.get("/api/auth/me", headers=ROH))
    me_rw = body(_client.get("/api/auth/me", headers=RWH))
    expect(me_ro.get("is_readonly") is True, "/me 对只读账号回 is_readonly=true", str(me_ro))
    expect(me_rw.get("is_readonly") is False, "/me 对普通账号回 is_readonly=false", str(me_rw))
    expect(me_ro.get("role") == "super_admin", "只读标记不影响 role 本身", str(me_ro.get("role")))

    # ————————————————————————————————————————————
    # 3) 读放行：只读账号照样能看
    # ————————————————————————————————————————————
    print("\n—— 读放行 ——")
    for path in ("/api/teams", "/api/projects", "/api/annotations",
                 "/api/qc-records", "/api/users/pending", "/api/audit-logs"):
        r = _client.get(path, headers=ROH)
        expect(r.status_code == 200, f"只读账号 GET {path} → 200",
               f"实际 {r.status_code} {body(r)}")

    # ————————————————————————————————————————————
    # 4) 写拦截：逐个 router 各打一发
    #    路径都指向本脚本自建的夹具（team 用上面的甲组，user 用 rw 自己），
    #    万一守卫漏挂，这些请求会**真的成功**——所以断言必须严格等于 403。
    #
    # ★ 凡是指向「库里真实存在的记录」的探针一律改用不存在的哨兵 id
    #   （999999999）。本脚本在 CI 里跑，但**也可以直接在生产库上跑**
    #   （README 的部署清单就是这么写的），所以「守卫漏挂」这个失败模式
    #   绝不能有破坏性副作用：写死的 id=1 一旦真的存在，漏挂就是一条真删除。
    #   用哨兵 id 断言强度不变——守卫漏挂时拿到的是 404，照样 FAIL。
    # ————————————————————————————————————————————
    print("\n—— 写拦截（逐 router）——")
    with SessionLocal() as db:
        tid = db.query(Team.id).filter(Team.name == f"{MARK}-甲组").scalar()

    writes = [
        ("POST", "/api/teams", {"name": f"{MARK}-不该建出来", "remark": ""}),
        ("PATCH", f"/api/teams/{tid}", {"name": f"{MARK}-不该改名"}),
        ("DELETE", f"/api/teams/{tid}", None),
        ("POST", "/api/projects", {"name": f"{MARK}-不该建出来"}),
        ("POST", "/api/annotations", {}),
        ("PATCH", "/api/annotations/999999999", {}),
        ("DELETE", "/api/annotations/999999999", None),
        ("POST", "/api/qc-records", {}),
        ("DELETE", "/api/qc-records/999999999", None),
        ("POST", "/api/work-records", {}),
        ("DELETE", "/api/work-records/999999999", None),
        ("POST", f"/api/users/{rw_id}/approve", {}),
        ("PATCH", f"/api/users/{rw_id}", {"name": f"{MARK}-不该改名"}),
        ("DELETE", f"/api/users/{rw_id}", None),
    ]
    for method, path, payload in writes:
        r = _client.request(method, path, headers=ROH, json=payload)
        expect(
            r.status_code == 403 and body(r).get("detail") == DETAIL,
            f"只读账号 {method} {path} → 403",
            f"实际 {r.status_code} {body(r)}",
        )

    # ★ 守卫是 router 级依赖，在 body 解析**之前**执行。
    #   所以哪怕 body 完全不合法，也该是 403 而不是 422——否则「先校验再拦」
    #   会让攻击面在下游接口上重新露出来。用空 body 打一个必填字段的接口。
    r = _client.post("/api/teams", headers=ROH, json={})
    expect(r.status_code == 403, "★ 非法 body 也是 403 而非 422（守卫先于 body 校验）",
           f"实际 {r.status_code} {body(r)}")

    # 夹具本身没被改动
    with SessionLocal() as db:
        t = db.query(Team).filter(Team.id == tid).first()
        expect(t is not None and t.name == f"{MARK}-甲组", "被拦截的写操作确实没落到库里",
               f"实际 {t.name if t else '已被删除'}")
        u = db.get(User, rw_id)
        expect(u is not None and u.name == f"{MARK}-正常", "被拦截的改账号操作没落库",
               f"实际 {u.name if u else '已被删除'}")

    # ————————————————————————————————————————————
    # 5) 不误伤：同一批写操作换成普通账号，断言**不是 403**
    #    这里只需要「不是 403」——具体是 201/200 还是 422 取决于 body，
    #    不是本脚本关心的。关心的是「守卫没有一刀切掉所有人」。
    # ————————————————————————————————————————————
    print("\n—— 不误伤正常账号 ——")
    # 这一轮是**真的会执行**的（普通账号没有守卫），所以每一条都必须
    # 要么落在自己的夹具上，要么因为 body 不合法而 422，要么指向哨兵 id。
    # 之前这里有一条 DELETE /api/annotations/1：在生产上就是真删一条标注。
    # 断言只需要「不是 403」，用哨兵 id 完全够，没必要拿真实数据当靶子。
    r = _client.post("/api/teams", headers=RWH, json={"name": f"{MARK}-乙组", "remark": ""})
    expect(r.status_code == 201, "普通账号 POST /api/teams → 201（守卫没一刀切）",
           f"实际 {r.status_code} {body(r)}")
    tid2 = body(r).get("id")
    if tid2:
        r2 = _client.patch(f"/api/teams/{tid2}", headers=RWH,
                           json={"name": f"{MARK}-乙组改"})
        expect(r2.status_code == 200, "普通账号 PATCH 自己建的团队 → 200",
               f"实际 {r2.status_code} {body(r2)}")

    for method, path, payload in [
        ("POST", "/api/projects", {"name": f"{MARK}-正常建"}),
        ("POST", "/api/annotations", {}),
        ("POST", "/api/qc-records", {}),
        ("POST", "/api/work-records", {}),
        ("DELETE", "/api/annotations/999999999", None),
    ]:
        r = _client.request(method, path, headers=RWH, json=payload)
        expect(r.status_code != 403, f"普通账号 {method} {path} 不是 403",
               f"实际 {r.status_code}（守卫误伤了普通账号）")

    # ————————————————————————————————————————————
    # 6) 未登录仍然是 401，没被守卫改写成 403
    #    （守卫依赖 get_current_user，认证该先于授权失败）
    # ————————————————————————————————————————————
    print("\n—— 未登录仍是 401 ——")
    r = _client.post("/api/teams", json={"name": "x", "remark": ""})
    expect(r.status_code == 401, "未带 token 的写请求仍是 401（没被改写成 403）",
           f"实际 {r.status_code} {body(r)}")

    # ————————————————————————————————————————————
    # 清理
    # ————————————————————————————————————————————
    print("\n—— 清理 ——")
    with SessionLocal() as db:
        db.query(Team).filter(Team.name.like(f"{MARK}-%")).delete(synchronize_session=False)
        db.query(User).filter(User.username.like(f"{MARK}_%")).delete(synchronize_session=False)
        db.commit()
        left = (
            db.query(Team).filter(Team.name.like(f"{MARK}-%")).count()
            + db.query(User).filter(User.username.like(f"{MARK}_%")).count()
        )
        expect(left == 0, "测试数据已清理干净", f"残留 {left} 条")

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
