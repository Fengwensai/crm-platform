from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..core.audit import log_action
from ..core.config import settings
from ..core.deps import get_current_user, is_manager
from ..core.netutil import client_ip
from ..db import get_db
from ..models.project import Project
from ..models.user import User
from ..models.work_record import WorkRecord
from ..schemas.work_record import WorkRecordCreate, WorkRecordOut, WorkRecordUpdate

router = APIRouter(prefix="/api/work-records", tags=["工作数据"])


# ————————————————————————————————————————————————
# 工具
# ————————————————————————————————————————————————
def _assert_date_allowed(d: date) -> None:
    """填报/修改的日期闸门：不能填未来，也不能翻旧账改历史。

    只对「改自己的数据」生效；管理者改员工数据不受此限（但会进审计日志）。
    """
    today = date.today()
    if d > today:
        raise HTTPException(status_code=422, detail="不能填报未来日期")
    if d < today - timedelta(days=settings.BACKFILL_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"只能填报或修改最近 {settings.BACKFILL_DAYS} 天内的数据",
        )


def _snapshot(r: WorkRecord) -> dict:
    """审计用快照。"""
    return {
        "work_date": r.work_date.isoformat(),
        "amount": r.amount,
        "rework_amount": r.rework_amount,
        "remark": r.remark,
    }


def _enrich(db: Session, rows: list[WorkRecord]) -> list[WorkRecordOut]:
    """补上展示用的 user_name / project_name / unit，省得前端再查一遍。"""
    if not rows:
        return []
    unames = dict(
        db.query(User.id, User.name)
        .filter(User.id.in_({r.user_id for r in rows}))
        .all()
    )
    projs = {
        p.id: p
        for p in db.query(Project)
        .filter(Project.id.in_({r.project_id for r in rows}))
        .all()
    }
    out: list[WorkRecordOut] = []
    for r in rows:
        p = projs.get(r.project_id)
        out.append(
            WorkRecordOut(
                id=r.id,
                user_id=r.user_id,
                user_name=unames.get(r.user_id, ""),
                project_id=r.project_id,
                project_name=p.name if p else "",
                unit=p.unit if p else "条",
                work_date=r.work_date,
                amount=r.amount,
                rework_amount=r.rework_amount,
                qualified=r.amount - r.rework_amount,
                remark=r.remark,
                edited_by_manager=r.edited_by_manager,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return out


# ————————————————————————————————————————————————
# 查
# ————————————————————————————————————————————————
@router.get("", response_model=list[WorkRecordOut])
def list_records(
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = None,
    user_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """工作数据列表。

    ★ 数据隔断在这里强制生效：员工**无条件**只查到自己，即使伪造 user_id
      参数也无效——不是「没传 user_id 才过滤」，而是「无论如何都盖掉」。
      前端藏按钮不算数，拦截必须在服务端。
    """
    q = db.query(WorkRecord)
    if is_manager(user):
        if user_id is not None:
            q = q.filter(WorkRecord.user_id == user_id)
    else:
        q = q.filter(WorkRecord.user_id == user.id)

    if project_id is not None:
        q = q.filter(WorkRecord.project_id == project_id)
    if date_from is not None:
        q = q.filter(WorkRecord.work_date >= date_from)
    if date_to is not None:
        q = q.filter(WorkRecord.work_date <= date_to)

    rows = (
        q.order_by(WorkRecord.work_date.desc(), WorkRecord.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return _enrich(db, rows)


# ————————————————————————————————————————————————
# 增
# ————————————————————————————————————————————————
@router.post("", response_model=WorkRecordOut, status_code=201)
def create_record(
    body: WorkRecordCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """填报工作数据。

    默认只给自己填。管理者可传 user_id 代某位员工补录（会进审计日志）；
    员工传的 user_id 一律被忽略——想给别人填也没有入口。
    """
    owner_id = user.id
    on_behalf = False
    if body.user_id is not None and is_manager(user) and body.user_id != user.id:
        target = db.get(User, body.user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="指定的员工不存在")
        owner_id, on_behalf = target.id, True

    _assert_date_allowed(body.work_date)

    project = db.get(Project, body.project_id)
    if project is None or project.status != "active":
        raise HTTPException(status_code=422, detail="项目不存在或已归档")

    dup = (
        db.query(WorkRecord)
        .filter(
            WorkRecord.user_id == owner_id,
            WorkRecord.project_id == body.project_id,
            WorkRecord.work_date == body.work_date,
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail="该日期、该项目已经填报过了，请直接修改那一条记录",
        )

    r = WorkRecord(
        user_id=owner_id,
        project_id=body.project_id,
        work_date=body.work_date,
        amount=body.amount,
        rework_amount=body.rework_amount,
        remark=body.remark.strip(),
        edited_by_manager=on_behalf,
    )
    db.add(r)
    db.flush()
    if on_behalf:
        log_action(
            db,
            actor=user,
            action="代填工作数据",
            target_type="work_record",
            target_id=r.id,
            summary=(
                f"为 {body.work_date} 代填 {body.amount}（返工 {body.rework_amount}）"
            ),
            detail={"after": _snapshot(r), "owner_id": owner_id},
            ip=client_ip(request),
        )
    db.commit()
    db.refresh(r)
    return _enrich(db, [r])[0]


# ————————————————————————————————————————————————
# 改
# ————————————————————————————————————————————————
@router.patch("/{rid}", response_model=WorkRecordOut)
def update_record(
    rid: int,
    body: WorkRecordUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(WorkRecord, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="记录不存在")

    mine = r.user_id == user.id
    if not mine and not is_manager(user):
        # 越权访问返回 404（而不是 403），不泄露「这条记录存在」
        raise HTTPException(status_code=404, detail="记录不存在")
    if mine:
        _assert_date_allowed(r.work_date)

    # 先算出目标值并校验，再落库——避免校验失败时对象已被改脏
    new_amount = body.amount if body.amount is not None else r.amount
    new_rework = (
        body.rework_amount if body.rework_amount is not None else r.rework_amount
    )
    if new_rework > new_amount:
        raise HTTPException(status_code=422, detail="返工量不能大于总量")

    before = _snapshot(r)
    r.amount = new_amount
    r.rework_amount = new_rework
    if body.remark is not None:
        r.remark = body.remark.strip()
    after = _snapshot(r)

    # 管理者动了员工的记录 → 留痕（改自己的不算）
    if not mine and before != after:
        r.edited_by_manager = True
        log_action(
            db,
            actor=user,
            action="修改工作数据",
            target_type="work_record",
            target_id=r.id,
            summary=f"记录 #{r.id}（{r.work_date}）{before} → {after}",
            detail={"before": before, "after": after, "owner_id": r.user_id},
            ip=client_ip(request),
        )

    db.commit()
    db.refresh(r)
    return _enrich(db, [r])[0]


# ————————————————————————————————————————————————
# 删
# ————————————————————————————————————————————————
@router.delete("/{rid}")
def delete_record(
    rid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(WorkRecord, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="记录不存在")

    mine = r.user_id == user.id
    if not mine and not is_manager(user):
        raise HTTPException(status_code=404, detail="记录不存在")
    if mine:
        _assert_date_allowed(r.work_date)

    if not mine:
        log_action(
            db,
            actor=user,
            action="删除工作数据",
            target_type="work_record",
            target_id=r.id,
            summary=f"记录 #{r.id}（{r.work_date}，{r.amount}）被管理者删除",
            detail={"before": _snapshot(r), "owner_id": r.user_id},
            ip=client_ip(request),
        )

    db.delete(r)
    db.commit()
    return {"ok": True}
