"""看板统计（双轨）。

————————————————————————————————————————————————————————————
★ 与 v1 最大的一处行为变更：这些端点从 `require_manager` 改成
  **`get_current_user` + 数据范围**。

  计划里写的是「保持 require_manager」，但同一份计划的菜单表又把「数据看板」
  列给了**组长**。两者不能同时成立——组长点进去会每个接口 403。
  组长角色的全部意义就是「看本组全部」，所以取前者：
  管理者看到全公司，组长看到本组，员工看到自己。
  `resolve_scope` 本来就是为这件事写的，用起来是零额外代码。

  唯一需要单独处理的是 `pending_count`（待审批账号数）：那是管理信息，
  非管理者恒为 0。见 schemas/stats.py。
————————————————————————————————————————————————————————————
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, is_manager
from ..core.scope import resolve_scope, visible_qc_filter
from ..core.tz import today_cn
from ..db import get_db
from ..models.annotation_record import AnnotationRecord
from ..models.project import Project
from ..models.qc_record import QcRecord
from ..models.user import User
from ..schemas.stats import (
    AnnotationSummaryOut,
    ByProjectRow,
    ByUserRow,
    OverviewOut,
    QcSummaryOut,
    TrendOut,
    TrendPoint,
)

router = APIRouter(prefix="/api/stats", tags=["统计"])


def _rate(numerator: int, denominator: int) -> float:
    """分母为 0 时给 0.0，**不做除法**。

    `0/0` 在 Python 里抛 ZeroDivisionError（500），在 JS 里是 NaN（页面显示
    「NaN%」）。两边都不是「没有数据」该有的样子，而且都要花很久才查得出来。
    ★ 「0 条 → 0.0」这条规则**只在服务端算**，前端不做 `total ? x : 0`——
      那种写法每个调用点都要记得写一次，漏一个就漏一个。
    """
    return round(numerator / denominator, 4) if denominator else 0.0


def _scope_label(user: User) -> str:
    """给卡片配的小字，消除「这个数是全公司还是本组」的歧义。

    由服务端算，因为范围本来就是服务端定的；前端再推一遍等于把同一个判断
    写成两处，改一处漏一处。
    """
    if is_manager(user):
        return "全公司"
    if user.role == "leader":
        # 注意这里**不检查** team_id 是否为空：没挂组的组长范围是空集，
        # 他看到的确实是 0，标签也确实是「本组」——如实描述即可。
        return "本组全量"
    return "本人"


def _resolve_range(
    date_from: date | None, date_to: date | None, default_days: int = 30
) -> tuple[date, date]:
    if date_to is None:
        date_to = today_cn()
    if date_from is None:
        date_from = date_to - timedelta(days=default_days - 1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


# ————————————————————————————————————————————————
# 概览
# ————————————————————————————————————————————————
@router.get("/overview", response_model=OverviewOut)
def overview(
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    df, dt = _resolve_range(date_from, date_to)
    scope = resolve_scope(db, user)

    box2d, box3d, anno_count = (
        db.query(
            func.coalesce(func.sum(AnnotationRecord.box2d), 0),
            func.coalesce(func.sum(AnnotationRecord.box3d), 0),
            func.count(AnnotationRecord.id),
        )
        .filter(
            scope.on(AnnotationRecord.user_id),
            AnnotationRecord.work_date.between(df, dt),
        )
        .one()
    )
    box2d, box3d, anno_count = int(box2d), int(box3d), int(anno_count)

    qc_total, qc_pass = (
        db.query(
            func.count(QcRecord.id),
            func.count(QcRecord.id).filter(QcRecord.result == "pass"),
        )
        .filter(
            visible_qc_filter(db, user),
            QcRecord.qc_date.between(df, dt),
        )
        .one()
    )
    qc_total, qc_pass = int(qc_total or 0), int(qc_pass or 0)

    # 人员计数同样受范围约束：管理者=全公司，组长=本组，员工=1
    employee_count = (
        db.query(func.count(User.id))
        .filter(User.role == "employee", scope.on(User.id))
        .scalar()
        or 0
    )
    active_employee_count = (
        db.query(func.count(User.id))
        .filter(User.role == "employee", User.status == "active", scope.on(User.id))
        .scalar()
        or 0
    )

    return OverviewOut(
        total_box2d=box2d,
        total_box3d=box3d,
        total_box=box2d + box3d,
        annotation_count=anno_count,
        qc_total=qc_total,
        qc_pass=qc_pass,
        qc_reject=qc_total - qc_pass,
        qc_pass_rate=_rate(qc_pass, qc_total),
        employee_count=int(employee_count),
        active_employee_count=int(active_employee_count),
        project_count=db.query(func.count(Project.id))
        .filter(Project.status == "active")
        .scalar()
        or 0,
        # ★ 仅管理者拿真值，非管理者恒为 0
        pending_count=(
            db.query(func.count(User.id)).filter(User.status == "pending").scalar() or 0
        )
        if is_manager(user)
        else 0,
        scope_label=_scope_label(user),
    )


# ————————————————————————————————————————————————
# 趋势
# ————————————————————————————————————————————————
def _trend_points(db: Session, df: date, dt: date, user: User) -> list[TrendPoint]:
    """按天聚合双轨，**并把没有数据的日期补成 0**。

    ★ 补零这一步不能省。漏掉的话，没有数据的那天在 `points` 里根本不存在，
      前端折线图会在那里**直接断线**——看起来像「那天系统挂了」，
      而不是「那天没人上班」。v1 就有这个循环，照搬。
    """
    scope = resolve_scope(db, user)

    anno = {
        row[0]: (int(row[1] or 0), int(row[2] or 0))
        for row in db.query(
            AnnotationRecord.work_date,
            func.coalesce(func.sum(AnnotationRecord.box2d), 0),
            func.coalesce(func.sum(AnnotationRecord.box3d), 0),
        )
        .filter(
            scope.on(AnnotationRecord.user_id),
            AnnotationRecord.work_date.between(df, dt),
        )
        .group_by(AnnotationRecord.work_date)
        .all()
    }
    qc = {
        row[0]: (int(row[1] or 0), int(row[2] or 0))
        for row in db.query(
            QcRecord.qc_date,
            func.count(QcRecord.id),
            func.count(QcRecord.id).filter(QcRecord.result == "pass"),
        )
        .filter(visible_qc_filter(db, user), QcRecord.qc_date.between(df, dt))
        .group_by(QcRecord.qc_date)
        .all()
    }

    points: list[TrendPoint] = []
    d = df
    while d <= dt:
        b2, b3 = anno.get(d, (0, 0))
        qt, qp = qc.get(d, (0, 0))
        points.append(
            TrendPoint(
                work_date=d,
                box2d=b2,
                box3d=b3,
                box_total=b2 + b3,
                qc_total=qt,
                qc_pass=qp,
                qc_reject=qt - qp,
            )
        )
        d += timedelta(days=1)
    return points


@router.get("/trend", response_model=TrendOut)
def trend(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dt = today_cn()
    df = dt - timedelta(days=days - 1)
    points = _trend_points(db, df, dt, user)
    return TrendOut(
        points=points,
        total_box2d=sum(p.box2d for p in points),
        total_box3d=sum(p.box3d for p in points),
        total_box=sum(p.box_total for p in points),
        qc_total=sum(p.qc_total for p in points),
        qc_pass=sum(p.qc_pass for p in points),
        qc_reject=sum(p.qc_reject for p in points),
    )


# ————————————————————————————————————————————————
# 按人
# ————————————————————————————————————————————————
@router.get("/by-user", response_model=list[ByUserRow])
def by_user(
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    df, dt = _resolve_range(date_from, date_to)
    scope = resolve_scope(db, user)

    anno_rows = (
        db.query(
            AnnotationRecord.user_id,
            func.sum(AnnotationRecord.box2d),
            func.sum(AnnotationRecord.box3d),
            func.count(AnnotationRecord.id),
            func.count(func.distinct(AnnotationRecord.work_date)),
        )
        .filter(
            scope.on(AnnotationRecord.user_id),
            AnnotationRecord.work_date.between(df, dt),
        )
        .group_by(AnnotationRecord.user_id)
        .all()
    )

    # ★ 质检要**分两个方向各查一次**，不能一次算完。
    #   一次算完必然要按某一列 group by，另一列的信息就丢了。
    by_inspector = {
        row[0]: (int(row[1]), int(row[2]))
        for row in db.query(
            QcRecord.inspector_id,
            func.count(QcRecord.id),
            func.count(QcRecord.id).filter(QcRecord.result == "pass"),
        )
        .filter(
            scope.on(QcRecord.inspector_id),  # 他判别人
            QcRecord.qc_date.between(df, dt),
        )
        .group_by(QcRecord.inspector_id)
        .all()
    }
    by_target = {
        row[0]: (int(row[1]), int(row[2]))
        for row in db.query(
            QcRecord.target_user_id,
            func.count(QcRecord.id),
            func.count(QcRecord.id).filter(QcRecord.result == "pass"),
        )
        .filter(
            scope.on(QcRecord.target_user_id),  # 别人判他
            QcRecord.qc_date.between(df, dt),
        )
        .group_by(QcRecord.target_user_id)
        .all()
    }

    uids = {r[0] for r in anno_rows} | set(by_inspector) | set(by_target)
    users = {u.id: u for u in db.query(User).filter(User.id.in_(uids)).all()} if uids else {}

    out: list[ByUserRow] = []
    for uid in uids:
        u = users.get(uid)
        row = next((r for r in anno_rows if r[0] == uid), None)
        b2 = int(row[1] or 0) if row else 0
        b3 = int(row[2] or 0) if row else 0
        ac = int(row[3] or 0) if row else 0
        days = int(row[4] or 0) if row else 0
        ins_t, ins_p = by_inspector.get(uid, (0, 0))
        tgt_t, tgt_p = by_target.get(uid, (0, 0))
        out.append(
            ByUserRow(
                user_id=uid,
                name=u.name if u else "",
                username=u.username if u else "",
                box2d=b2,
                box3d=b3,
                box_total=b2 + b3,
                annotation_count=ac,
                days=days,
                qc_as_inspector_total=ins_t,
                qc_as_inspector_pass=ins_p,
                qc_as_inspector_pass_rate=_rate(ins_p, ins_t),
                qc_as_target_total=tgt_t,
                qc_as_target_pass=tgt_p,
                qc_as_target_pass_rate=_rate(tgt_p, tgt_t),
            )
        )
    out.sort(key=lambda x: x.box_total, reverse=True)
    return out


# ————————————————————————————————————————————————
# 按项目
# ————————————————————————————————————————————————
@router.get("/by-project", response_model=list[ByProjectRow])
def by_project(
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    df, dt = _resolve_range(date_from, date_to)
    scope = resolve_scope(db, user)

    anno_rows = (
        db.query(
            AnnotationRecord.project_id,
            func.sum(AnnotationRecord.box2d),
            func.sum(AnnotationRecord.box3d),
            func.count(AnnotationRecord.id),
            func.count(func.distinct(AnnotationRecord.user_id)),
        )
        .filter(
            scope.on(AnnotationRecord.user_id),
            AnnotationRecord.work_date.between(df, dt),
        )
        .group_by(AnnotationRecord.project_id)
        .all()
    )
    qc_rows = (
        db.query(
            QcRecord.project_id,
            func.count(QcRecord.id),
            func.count(QcRecord.id).filter(QcRecord.result == "pass"),
        )
        .filter(
            scope.on(QcRecord.inspector_id),
            QcRecord.qc_date.between(df, dt),
        )
        .group_by(QcRecord.project_id)
        .all()
    )
    qc_map = {r[0]: (int(r[1]), int(r[2])) for r in qc_rows}

    pids = {r[0] for r in anno_rows} | set(qc_map)
    projs = (
        {p.id: p for p in db.query(Project).filter(Project.id.in_(pids)).all()}
        if pids
        else {}
    )

    out: list[ByProjectRow] = []
    for pid in pids:
        p = projs.get(pid)
        row = next((r for r in anno_rows if r[0] == pid), None)
        b2 = int(row[1] or 0) if row else 0
        b3 = int(row[2] or 0) if row else 0
        ac = int(row[3] or 0) if row else 0
        people = int(row[4] or 0) if row else 0
        qt, qp = qc_map.get(pid, (0, 0))
        out.append(
            ByProjectRow(
                project_id=pid,
                code=p.code if p else "",
                name=p.name if p else "",
                box2d=b2,
                box3d=b3,
                box_total=b2 + b3,
                annotation_count=ac,
                people=people,
                qc_total=qt,
                qc_pass=qp,
                qc_reject=qt - qp,
                qc_pass_rate=_rate(qp, qt),
            )
        )
    out.sort(key=lambda x: x.box_total, reverse=True)
    return out


# ————————————————————————————————————————————————
# 记录页顶部的统计卡
# ————————————————————————————————————————————————
@router.get("/annotation-summary", response_model=AnnotationSummaryOut)
def annotation_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """标注记录页的 4 张卡：今日标注人数 / 今日工作量 / 总工作量 / 参与人数。

    ★ **不接受任何筛选参数**（见 schemas 里的说明）：卡片在筛选条上面，
      「今日工作量」配上「开始日期 = 上个月」本就自相矛盾。
      只受数据范围约束。

    ★ 「今日」用 `today_cn()` 而不是 `date.today()`：服务端时区意识，
      详见 core/tz.py。CI 跑在 UTC，用本地日期会在每天 08:00 前算错一整天。
    """
    scope = resolve_scope(db, user)
    today = today_cn()

    today_people = (
        db.query(func.count(func.distinct(AnnotationRecord.user_id)))
        .filter(scope.on(AnnotationRecord.user_id), AnnotationRecord.work_date == today)
        .scalar()
        or 0
    )
    today_box = (
        db.query(
            func.coalesce(
                func.sum(AnnotationRecord.box2d + AnnotationRecord.box3d), 0
            )
        )
        .filter(scope.on(AnnotationRecord.user_id), AnnotationRecord.work_date == today)
        .scalar()
        or 0
    )
    total_box = (
        db.query(
            func.coalesce(
                func.sum(AnnotationRecord.box2d + AnnotationRecord.box3d), 0
            )
        )
        .filter(scope.on(AnnotationRecord.user_id))
        .scalar()
        or 0
    )
    people = (
        db.query(func.count(func.distinct(AnnotationRecord.user_id)))
        .filter(scope.on(AnnotationRecord.user_id))
        .scalar()
        or 0
    )

    return AnnotationSummaryOut(
        today_people=int(today_people),
        today_box=int(today_box),
        total_box=int(total_box),
        people=int(people),
        scope_label=_scope_label(user),
    )


@router.get("/qc-summary", response_model=QcSummaryOut)
def qc_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """质检记录页的 3 张卡：总记录数 / 通过 / 打回。

    可见性与质检列表**用的是同一个谓词**（`visible_qc_filter`），
    所以卡片的 `total` 恒等于不带任何筛选的列表 `total`。
    两处各写一遍的话，用户会发现「卡片说 120 条，列表只列出 87 条」。
    """
    total, passed = (
        db.query(
            func.count(QcRecord.id),
            func.count(QcRecord.id).filter(QcRecord.result == "pass"),
        )
        .filter(visible_qc_filter(db, user))
        .one()
    )
    total, passed = int(total or 0), int(passed or 0)
    return QcSummaryOut(
        total=total,
        passed=passed,
        rejected=total - passed,
        scope_label=_scope_label(user),
    )
