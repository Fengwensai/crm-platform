from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.audit import log_action
from ..core.deps import require_manager
from ..core.guards import count_user_records, format_counts
from ..core.netutil import client_ip
from ..core.security import hash_password
from ..db import get_db
from ..models.user import User
from ..schemas.user import ReviewIn, UserOut, UserUpdateIn

router = APIRouter(prefix="/api/users", tags=["账号"])

VALID_ROLES = ("super_admin", "manager", "employee")


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
    return q.order_by(User.id.asc()).all()


@router.get("/pending", response_model=list[UserOut])
def list_pending(
    manager: User = Depends(require_manager), db: Session = Depends(get_db)
):
    """待审批账号（注册后卡在这里，登不上）。先来先审。"""
    return (
        db.query(User)
        .filter(User.status == "pending")
        .order_by(User.created_at.asc())
        .all()
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
    return u


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
    return u


@router.patch("/{uid}", response_model=UserOut)
def update_user(
    uid: int,
    body: UserUpdateIn,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """改名 / 启停 / 重置密码；角色变更仅超管可做。"""
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 管理者动不了超管账号（防越权）；超管自己可以被超管改
    if u.role == "super_admin" and manager.role != "super_admin":
        raise HTTPException(status_code=403, detail="不能修改超级管理员账号")

    changes: list[str] = []

    if body.role is not None and body.role != u.role:
        if manager.role != "super_admin":
            raise HTTPException(status_code=403, detail="只有超级管理员可以变更角色")
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=422, detail="角色无效")
        # 防呆：不能把最后一个在用的超管降级，否则没人能再改角色了
        if u.role == "super_admin" and _count_super_admins(db, exclude_id=u.id) == 0:
            raise HTTPException(status_code=422, detail="至少要保留一个超级管理员")
        changes.append(f"角色 {u.role} → {body.role}")
        u.role = body.role

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
    return u


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
