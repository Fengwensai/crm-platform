from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_manager
from ..db import get_db
from ..models.project import Project
from ..models.user import User
from ..models.work_record import WorkRecord
from ..schemas.stats import (
    ByProjectRow,
    ByUserRow,
    MyStatsOut,
    OverviewOut,
    TrendOut,
    TrendPoint,
)

router = APIRouter(prefix="/api/stats", tags=["统计"])


def _resolve_range(
    date_from: date | None, date_to: date | None, default_days: int = 30
) -> tuple[date, date]:
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=default_days - 1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _rate(qualified: int, total: int) -> float:
    return round(qualified / total, 4) if total else 0.0


def _trend_points(db: Session, df: date, dt: date, user_id: int | None = None):
    """按天聚合，并把没有数据的日期补成 0——否则前端折线图会断线。"""
    q = db.query(
        WorkRecord.work_date,
        func.sum(WorkRecord.amount),
        func.sum(WorkRecord.rework_amount),
    ).filter(WorkRecord.work_date.between(df, dt))
    if user_id is not None:
        q = q.filter(WorkRecord.user_id == user_id)
    got = {
        row[0]: (int(row[1] or 0), int(row[2] or 0))
        for row in q.group_by(WorkRecord.work_date).all()
    }
    points: list[TrendPoint] = []
    d = df
    while d <= dt:
        amount, rework = got.get(d, (0, 0))
        points.append(
            TrendPoint(
                work_date=d, amount=amount, rework=rework, qualified=amount - rework
            )
        )
        d += timedelta(days=1)
    return points


# ————————————————————————————————————————————————
# 管理者：整体数据走向
# ————————————————————————————————————————————————
@router.get("/overview", response_model=OverviewOut)
def overview(
    date_from: date | None = None,
    date_to: date | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    df, dt = _resolve_range(date_from, date_to)
    amount, rework, count = (
        db.query(
            func.coalesce(func.sum(WorkRecord.amount), 0),
            func.coalesce(func.sum(WorkRecord.rework_amount), 0),
            func.count(WorkRecord.id),
        )
        .filter(WorkRecord.work_date.between(df, dt))
        .one()
    )
    amount, rework = int(amount), int(rework)
    return OverviewOut(
        total_amount=amount,
        total_rework=rework,
        total_qualified=amount - rework,
        pass_rate=_rate(amount - rework, amount),
        record_count=int(count),
        employee_count=db.query(func.count(User.id))
        .filter(User.role == "employee")
        .scalar()
        or 0,
        active_employee_count=db.query(func.count(User.id))
        .filter(User.role == "employee", User.status == "active")
        .scalar()
        or 0,
        project_count=db.query(func.count(Project.id))
        .filter(Project.status == "active")
        .scalar()
        or 0,
        pending_count=db.query(func.count(User.id))
        .filter(User.status == "pending")
        .scalar()
        or 0,
    )


@router.get("/trend", response_model=TrendOut)
def trend(
    days: int = Query(default=30, ge=1, le=365),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    dt = date.today()
    df = dt - timedelta(days=days - 1)
    points = _trend_points(db, df, dt)
    return TrendOut(
        points=points,
        total_amount=sum(p.amount for p in points),
        total_rework=sum(p.rework for p in points),
    )


@router.get("/by-user", response_model=list[ByUserRow])
def by_user(
    date_from: date | None = None,
    date_to: date | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    df, dt = _resolve_range(date_from, date_to)
    rows = (
        db.query(
            WorkRecord.user_id,
            func.sum(WorkRecord.amount),
            func.sum(WorkRecord.rework_amount),
            func.count(func.distinct(WorkRecord.work_date)),
        )
        .filter(WorkRecord.work_date.between(df, dt))
        .group_by(WorkRecord.user_id)
        .all()
    )
    users = {
        u.id: u
        for u in db.query(User).filter(User.id.in_([r[0] for r in rows])).all()
    } if rows else {}

    out: list[ByUserRow] = []
    for uid, amount, rework, days in rows:
        amount, rework = int(amount or 0), int(rework or 0)
        u = users.get(uid)
        out.append(
            ByUserRow(
                user_id=uid,
                name=u.name if u else "",
                username=u.username if u else "",
                amount=amount,
                rework=rework,
                qualified=amount - rework,
                pass_rate=_rate(amount - rework, amount),
                days=int(days or 0),
            )
        )
    out.sort(key=lambda x: x.amount, reverse=True)
    return out


@router.get("/by-project", response_model=list[ByProjectRow])
def by_project(
    date_from: date | None = None,
    date_to: date | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    df, dt = _resolve_range(date_from, date_to)
    rows = (
        db.query(
            WorkRecord.project_id,
            func.sum(WorkRecord.amount),
            func.sum(WorkRecord.rework_amount),
            func.count(func.distinct(WorkRecord.user_id)),
        )
        .filter(WorkRecord.work_date.between(df, dt))
        .group_by(WorkRecord.project_id)
        .all()
    )
    projs = {
        p.id: p
        for p in db.query(Project)
        .filter(Project.id.in_([r[0] for r in rows]))
        .all()
    } if rows else {}

    out: list[ByProjectRow] = []
    for pid, amount, rework, people in rows:
        amount, rework = int(amount or 0), int(rework or 0)
        p = projs.get(pid)
        out.append(
            ByProjectRow(
                project_id=pid,
                code=p.code if p else "",
                name=p.name if p else "",
                unit=p.unit if p else "条",
                amount=amount,
                rework=rework,
                qualified=amount - rework,
                pass_rate=_rate(amount - rework, amount),
                people=int(people or 0),
            )
        )
    out.sort(key=lambda x: x.amount, reverse=True)
    return out


# ————————————————————————————————————————————————
# 员工：我的统计（★ 同样强制只算自己）
# ————————————————————————————————————————————————
@router.get("/me", response_model=MyStatsOut)
def my_stats(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dt = date.today()
    df = dt - timedelta(days=days - 1)

    amount, rework, day_count = (
        db.query(
            func.coalesce(func.sum(WorkRecord.amount), 0),
            func.coalesce(func.sum(WorkRecord.rework_amount), 0),
            func.count(func.distinct(WorkRecord.work_date)),
        )
        .filter(WorkRecord.user_id == user.id, WorkRecord.work_date.between(df, dt))
        .one()
    )
    amount, rework = int(amount), int(rework)

    rows = (
        db.query(
            WorkRecord.project_id,
            func.sum(WorkRecord.amount),
            func.sum(WorkRecord.rework_amount),
            func.count(func.distinct(WorkRecord.user_id)),
        )
        .filter(WorkRecord.user_id == user.id, WorkRecord.work_date.between(df, dt))
        .group_by(WorkRecord.project_id)
        .all()
    )
    projs = {
        p.id: p
        for p in db.query(Project)
        .filter(Project.id.in_([r[0] for r in rows]))
        .all()
    } if rows else {}

    by_project: list[ByProjectRow] = []
    for pid, a, rw, people in rows:
        a, rw = int(a or 0), int(rw or 0)
        p = projs.get(pid)
        by_project.append(
            ByProjectRow(
                project_id=pid,
                code=p.code if p else "",
                name=p.name if p else "",
                unit=p.unit if p else "条",
                amount=a,
                rework=rw,
                qualified=a - rw,
                pass_rate=_rate(a - rw, a),
                people=int(people or 0),
            )
        )
    by_project.sort(key=lambda x: x.amount, reverse=True)

    return MyStatsOut(
        total_amount=amount,
        total_rework=rework,
        total_qualified=amount - rework,
        pass_rate=_rate(amount - rework, amount),
        days=int(day_count or 0),
        trend=_trend_points(db, df, dt, user_id=user.id),
        by_project=by_project,
    )
