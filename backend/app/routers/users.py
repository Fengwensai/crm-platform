from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.audit import log_action
from ..core.deps import get_current_user, require_manager
from ..core.guards import count_user_records, format_counts
from ..core.netutil import client_ip
from ..core.security import hash_password
from ..core.scope import resolve_scope
from ..db import get_db
from ..models.team import Team
from ..models.user import User
from ..schemas.user import ReviewIn, UserOption, UserOut, UserUpdateIn

router = APIRouter(prefix="/api/users", tags=["账号"])

# 四种角色。MANAGER_ROLES（manager / super_admin）定义在 core/scope.py，
# 因为「谁是管理者」同时决定了数据可见范围，那个定义必须只有一份。
VALID_ROLES = ("super_admin", "manager", "leader", "employee")


# ————————————————————————————————————————————————
# 展示字段：批量补 team_name
# ————————————————————————————————————————————————
def _team_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    real = {i for i in ids if i is not None}
    if not real:
        return {}
    return dict(db.query(Team.id, Team.name).filter(Team.id.in_(real)).all())


def _user_out(u: User, team_name: str = "") -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        name=u.name,
        role=u.role,
        status=u.status,
        team_id=u.team_id,
        team_name=team_name,
        created_at=u.created_at,
        reviewed_at=u.reviewed_at,
        review_note=u.review_note or "",
    )


def _enrich_users(db: Session, users: list[User]) -> list[UserOut]:
    """一次查完所有 team_name，避免每行 lazy load 一次。

    ★ 用显式构造而不是 `from_attributes` 直接吐 ORM 对象：`team_name` 不是
      模型字段，靠 from_attributes 是取不到的，而给 User 加一个 relationship
      会让「渲染一页 50 个用户」变成「50 次数据库往返」。
    """
    names = _team_names(db, {u.team_id for u in users})
    return [_user_out(u, names.get(u.team_id, "")) for u in users]


def _assert_leader_config(
    db: Session, role: str, team_id: int | None, *, exclude_id: int
) -> None:
    """组长的配置约束：**必须有组，且一个组只能有一个组长**。

    ★ 必须在「角色」和「团队」两个字段**都算完之后**整体校验，不能各查各的：
      分开看的话，`{team_id: null}`（把在任组长移出团队）和
      `{role: 'leader'}`（把已有组员提成组长）单独传给同一个接口都是合法的，
      合起来的结果却是一个没有组的组长、或者一个组两个组长。

      前者不会崩——`core/scope.py` 会把「没挂组的组长」解析成**空集**，
      于是他登录后什么都看不见，而界面上他还是组长。这种故障没人能自己诊断。
    """
    if role != "leader":
        return
    if team_id is None:
        raise HTTPException(
            status_code=422, detail="组长必须属于一个团队；请先指定团队或改为其它角色"
        )
    other = (
        db.query(User.id)
        .filter(User.role == "leader", User.team_id == team_id, User.id != exclude_id)
        .first()
    )
    if other is not None:
        raise HTTPException(
            status_code=422, detail="该团队已有组长，请先解除原组长的身份"
        )


def _count_super_admins(db: Session, exclude_id: int | None = None) -> int:
    q = db.query(User).filter(User.role == "super_admin", User.status == "active")
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    return q.count()


@router.get("", response_model=list[UserOut])
def list_users(
    status: str | None = None,
    role: str | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if status:
        q = q.filter(User.status == status)
    if role:
        q = q.filter(User.role == role)
    return _enrich_users(db, q.order_by(User.id.asc()).all())


# ★ 声明位置必须在 `/{uid}` 之前。
#   `include_router` 按声明顺序匹配，`/options` 若排在 `/{uid}`（或 `/{uid}/...`）之后，
#   会被路径参数吃掉，表现为「选项接口返回 404 账号不存在」这种莫名其妙的错。
@router.get("/options", response_model=list[UserOption])
def list_options(
    all: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """人员下拉选项。**不走 `/api/users`**——那个是管理者专属，会连审批信息
    一起吐出来（组长拿到它就等于拿到全公司名册 + 谁在等审批）。

    两种用途，由 `all` 显式区分：

    | 调用方 | all | 拿到谁 |
    |---|---|---|
    | 标注页「代填给谁」 | false（默认） | 自己范围内的人：员工=只有自己，组长=本组，管理者=全员 |
    | 质检页「被质检人员」 | true | **全公司在职员工** |

    ★ 为什么质检要全量：员工之间互相质检是常态，跨组质检也一定会有。
      若按范围收窄，员工的下拉里只剩他自己，而「不能质检自己」又拦掉那一条——
      整个质检页对员工就填不出任何东西。已与用户确认。

    ★ `all` 默认 false，宽的必须显式要。任何「信息不全时」的失败都该偏向窄的那边。

    ★ 只返回 `status='active'`：停用的账号没法登录，给他填数据只会变成
      谁也看不见的孤儿记录。
    """
    q = db.query(User).filter(User.status == "active")
    if not all:
        q = q.filter(resolve_scope(db, user).on(User.id))
    users = q.order_by(User.id.asc()).all()

    names = _team_names(db, {u.team_id for u in users})
    return [
        UserOption(
            id=u.id,
            name=u.name,
            username=u.username,
            role=u.role,
            team_id=u.team_id,
            team_name=names.get(u.team_id, ""),
        )
        for u in users
    ]


@router.get("/pending", response_model=list[UserOut])
def list_pending(
    manager: User = Depends(require_manager), db: Session = Depends(get_db)
):
    """待审批账号（注册后卡在这里，登不上）。先来先审。"""
    return _enrich_users(
        db,
        db.query(User)
        .filter(User.status == "pending")
        .order_by(User.created_at.asc())
        .all(),
    )


@router.post("/{uid}/approve", response_model=UserOut)
def approve_user(
    uid: int,
    body: ReviewIn,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if u.status != "pending":
        raise HTTPException(status_code=422, detail="该账号不在待审批状态")

    u.status = "active"
    u.reviewed_by = manager.id
    u.reviewed_at = datetime.now(timezone.utc)
    u.review_note = body.note.strip()
    log_action(
        db,
        actor=manager,
        action="审批通过",
        target_type="user",
        target_id=u.id,
        summary=f"{u.name}（工号 {u.username}）注册申请已通过",
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(u)
    return _enrich_users(db, [u])[0]


@router.post("/{uid}/reject", response_model=UserOut)
def reject_user(
    uid: int,
    body: ReviewIn,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if u.status != "pending":
        raise HTTPException(status_code=422, detail="该账号不在待审批状态")

    u.status = "rejected"
    u.reviewed_by = manager.id
    u.reviewed_at = datetime.now(timezone.utc)
    u.review_note = body.note.strip()
    log_action(
        db,
        actor=manager,
        action="审批驳回",
        target_type="user",
        target_id=u.id,
        summary=f"{u.name}（工号 {u.username}）注册申请被驳回：{u.review_note or '未填原因'}",
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(u)
    return _enrich_users(db, [u])[0]


@router.patch("/{uid}", response_model=UserOut)
def update_user(
    uid: int,
    body: UserUpdateIn,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """改名 / 启停 / 调组 / 重置密码；角色变更仅超管可做。

    ★ 全部**先算目标值并整体校验，最后才落库**（沿用 v1 的写法）。
      逐字段「校验完就赋值」的话，一处在中间抛错，前面的字段已经被改脏了——
      而这个 session 不会被提交，于是错误信息说的是「B 不合法」，
      用户改完 B 再提交，A 又悄悄丢了一次。先算后写就没有这个中间态。
    """
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 管理者动不了超管账号（防越权）；超管自己可以被超管改
    if u.role == "super_admin" and manager.role != "super_admin":
        raise HTTPException(status_code=403, detail="不能修改超级管理员账号")

    changes: list[str] = []

    # —— 1. 算角色 ——
    new_role = u.role
    if body.role is not None and body.role != u.role:
        if manager.role != "super_admin":
            raise HTTPException(status_code=403, detail="只有超级管理员可以变更角色")
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=422, detail="角色无效")
        # 防呆：不能把最后一个在用的超管降级，否则没人能再改角色了
        if u.role == "super_admin" and _count_super_admins(db, exclude_id=u.id) == 0:
            raise HTTPException(status_code=422, detail="至少要保留一个超级管理员")
        new_role = body.role

    # —— 2. 算团队 ——
    new_team = u.team_id
    team_touched = "team_id" in body.model_fields_set and body.team_id != u.team_id
    if team_touched and body.team_id is not None:
        t = db.get(Team, body.team_id)
        if t is None or t.status != "active":
            raise HTTPException(status_code=422, detail="团队不存在或已归档")
        new_team = body.team_id
    elif team_touched:
        new_team = None

    # —— 3. 两个字段合起来校验（组长必须有组、一组一个组长）——
    _assert_leader_config(db, new_role, new_team, exclude_id=u.id)

    # —— 4. 校验全过，落库 ——
    if new_role != u.role:
        changes.append(f"角色 {u.role} → {new_role}")
        u.role = new_role

    if team_touched:
        tnames = _team_names(db, {u.team_id, new_team})
        changes.append(
            f"团队「{tnames.get(u.team_id, '未分配')}」→「{tnames.get(new_team, '未分配')}」"
        )
        u.team_id = new_team

    if body.name is not None and body.name.strip() != u.name:
        changes.append(f"姓名「{u.name}」→「{body.name.strip()}」")
        u.name = body.name.strip()

    if body.status is not None and body.status != u.status:
        if body.status not in ("active", "disabled"):
            raise HTTPException(status_code=422, detail="状态只能是 active 或 disabled")
        if u.id == manager.id:
            raise HTTPException(status_code=422, detail="不能停用自己")
        if u.role == "super_admin" and _count_super_admins(db, exclude_id=u.id) == 0:
            raise HTTPException(status_code=422, detail="至少要保留一个超级管理员")
        changes.append(f"状态 {u.status} → {body.status}")
        u.status = body.status

    password_reset = False
    if body.password:
        u.password_hash = hash_password(body.password)
        password_reset = True

    if changes or password_reset:
        summary = f"{u.name}（工号 {u.username}）：" + "；".join(changes or ["重置密码"])
        log_action(
            db,
            actor=manager,
            action="修改账号",
            target_type="user",
            target_id=u.id,
            summary=summary,
            ip=client_ip(request),
        )
    db.commit()
    db.refresh(u)
    return _enrich_users(db, [u])[0]


@router.delete("/{uid}")
def delete_user(
    uid: int,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """删除账号。有任何历史数据的不允许删（会变孤儿数据）——应改为「停用」。

    ★ 守卫查的是**标注 + 质检 + v1 填报**三处，见 core/guards.py。
      只查其中一张表的话，删除会「成功」，那人名下的其它记录当场变成孤儿。
    """
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if u.id == manager.id:
        raise HTTPException(status_code=422, detail="不能删除自己")
    if u.role == "super_admin":
        raise HTTPException(status_code=403, detail="不能删除超级管理员账号")

    counts = count_user_records(db, uid)
    if counts:
        raise HTTPException(
            status_code=422,
            detail=f"该账号已有{format_counts(counts)}，不能删除；请改为「停用」",
        )

    log_action(
        db,
        actor=manager,
        action="删除账号",
        target_type="user",
        target_id=u.id,
        summary=f"{u.name}（工号 {u.username}，{u.status}）",
        ip=client_ip(request),
    )
    db.delete(u)
    db.commit()
    return {"ok": True}
