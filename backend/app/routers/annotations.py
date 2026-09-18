"""标注工作量（双轨之一）。

v1 的「数量 + 返工量」在这里被取代：一条标注记录 = 「条目号 + 2D 框数 + 3D 框数」。
工作量口径 = `box2d + box3d`。

————————————————————————————————————————————————————————————
本文件的两条结构性约定（抄改此文件前先读这里）：

**① 查询只有一个构造入口 `_scoped_query`。**
   list / export / （将来的任何聚合）全走它。方言平台那边 list 与 export 是
   **逐行重复的两遍筛选逻辑**，而且已经漂移了（export 多一个 `sort_by`、
   list 多一个 `exclude_task_id`）——同一组筛选条件在两个接口返回不同的行，
   用户导出对不上列表，只能怀疑人生。这里从构造上不给漂移留位置。

**② scope 永远第一个盖上去。**
   用户传的 `user_id` 只能在 scope **之上**再收窄（`filter` 是 AND），
   所以 `?user_id=<别组的人>` 的结果是**空列表**，不可能放大范围。
   方言平台那种「先按 role 分支、再各自拼筛选」的写法，漏一个分支就是越权。
"""

from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, aliased

from ..core.audit import log_action
from ..core.deps import get_current_user
from ..core.netutil import client_ip
from ..core.rules import assert_date_allowed, resolve_owner
from ..core.scope import assert_can_touch, resolve_scope
from ..core.tz import today_cn
from ..db import get_db
from ..models.annotation_record import AnnotationRecord
from ..models.project import Project
from ..models.user import User
from ..schemas.annotation import (
    AnnotationCreate,
    AnnotationOut,
    AnnotationPage,
    AnnotationUpdate,
)
from ..services.export import assert_export_size, csv_response

router = APIRouter(prefix="/api/annotations", tags=["标注"])

# 导出列名用中文。与方言平台那份英文列名（recording_id / task_name…）**有意不同**：
# 那些是给开发者对账的原始字段，而这里导出的表格是给标注公司行政直接丢进 Excel
# 看的，「box2d」这种列名对他们没有意义。为可读性牺牲跨仓库一致性。
EXPORT_COLUMNS = [
    "记录ID",
    "标注人",
    "项目",
    "日期",
    "条目号",
    "2D框数",
    "3D框数",
    "合计框数",
    "备注",
    "是否被管理者修改",
    "填报时间",
]


# ————————————————————————————————————————————————
# 筛选条件：list 与 export 共用的同一个对象
# ————————————————————————————————————————————————
@dataclass
class AnnotationFilters:
    date_from: date | None = None
    date_to: date | None = None
    project_id: int | None = None
    user_id: int | None = None


def annotation_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = None,
    user_id: int | None = None,
) -> AnnotationFilters:
    """做成 FastAPI 依赖，是为了让两个接口**拿到的是同一个类型**。

    手写两遍 `def list(...)` / `def export(...)` 的参数表，总有一天会只给
    其中一个加参数（这正是方言平台已经发生的事）。同一个依赖对象，
    加了就是两边一起加。
    """
    return AnnotationFilters(
        date_from=date_from,
        date_to=date_to,
        project_id=project_id,
        user_id=user_id,
    )


# ————————————————————————————————————————————————
# 唯一查询入口
# ————————————————————————————————————————————————
def _scoped_query(db: Session, user: User, f: AnnotationFilters):
    scope = resolve_scope(db, user)
    # ★ 先盖 scope（见文件头 ②）
    q = db.query(AnnotationRecord).filter(scope.on(AnnotationRecord.user_id))
    if f.user_id is not None:
        q = q.filter(AnnotationRecord.user_id == f.user_id)
    if f.project_id is not None:
        q = q.filter(AnnotationRecord.project_id == f.project_id)
    if f.date_from is not None:
        q = q.filter(AnnotationRecord.work_date >= f.date_from)
    if f.date_to is not None:
        q = q.filter(AnnotationRecord.work_date <= f.date_to)
    return q


def _dup_ids(db: Session, ids: list[int]) -> set[int]:
    """这一页里，哪些行的「同人 + 同项目 + 同天 + 同条目号」不止一条。

    ★ 不落库、每次现算：这个判断会随数据增删而改变，存下来就等于把
      「当时看起来像重复」冻结成事实，之后再也说不清。

    ★ 用 `EXISTS` + 相关子查询，正好命中 `ix_anno_dup_probe`
      （user_id, project_id, work_date, item_no）这条为它铺的复合索引。
      EXISTS 的判定条件**不带 scope**——「疑似重复」是数据本身的性质；
      外层已经按 scope 过滤过，同一个人只会出现在他该出现的地方。
    """
    if not ids:
        return set()
    other = aliased(AnnotationRecord)
    rows = (
        db.query(AnnotationRecord.id)
        .filter(
            AnnotationRecord.id.in_(ids),
            db.query(other.id)
            .filter(
                other.user_id == AnnotationRecord.user_id,
                other.project_id == AnnotationRecord.project_id,
                other.work_date == AnnotationRecord.work_date,
                other.item_no == AnnotationRecord.item_no,
                other.id != AnnotationRecord.id,
            )
            .exists(),
        )
        .all()
    )
    return {r[0] for r in rows}


def _enrich(db: Session, rows: list[AnnotationRecord]) -> list[AnnotationOut]:
    """补展示字段（人名 / 项目名）+ 现算「疑似重复」。"""
    if not rows:
        return []
    unames = dict(
        db.query(User.id, User.name)
        .filter(User.id.in_({r.user_id for r in rows}))
        .all()
    )
    pnames = dict(
        db.query(Project.id, Project.name)
        .filter(Project.id.in_({r.project_id for r in rows}))
        .all()
    )
    dups = _dup_ids(db, [r.id for r in rows])
    return [
        AnnotationOut(
            id=r.id,
            user_id=r.user_id,
            user_name=unames.get(r.user_id, ""),
            project_id=r.project_id,
            project_name=pnames.get(r.project_id, ""),
            work_date=r.work_date,
            item_no=r.item_no,
            box2d=r.box2d,
            box3d=r.box3d,
            box_total=r.box2d + r.box3d,
            remark=r.remark,
            edited_by_manager=r.edited_by_manager,
            suspected_duplicate=r.id in dups,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def _snapshot(r: AnnotationRecord) -> dict:
    return {
        "work_date": r.work_date.isoformat(),
        "item_no": r.item_no,
        "box2d": r.box2d,
        "box3d": r.box3d,
        "remark": r.remark,
    }


def _check_project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.status != "active":
        raise HTTPException(status_code=422, detail="项目不存在或已归档")
    return p


# ————————————————————————————————————————————————
# 查
# ————————————————————————————————————————————————
@router.get("", response_model=AnnotationPage)
def list_annotations(
    f: AnnotationFilters = Depends(annotation_filters),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """标注记录列表。

    返回 `{items, total}` 而不是裸数组：前端要分页，而且**导出行数必须能
    和同参数的 total 对账**（回归里有一条断言就钉这个）——裸数组给不出总数，
    「导出和列表对不上」这类问题就永远发现不了。
    """
    q = _scoped_query(db, user, f)
    total = q.count()
    rows = (
        q.order_by(AnnotationRecord.work_date.desc(), AnnotationRecord.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AnnotationPage(items=_enrich(db, rows), total=total)


@router.get("/export")
def export_annotations(
    f: AnnotationFilters = Depends(annotation_filters),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出 CSV。

    ★ 先 `count()` 再 `all()`，且中间必须过 `assert_export_size`：
      先取行再检查的话，内存已经被吃掉了，检查就没有意义。
      详见 services/export.py 里那段关于「同机方言平台被 OOM 连带拖垮」的注释。

    ★ 导出**复用 `_scoped_query`**，所以员工导出的只有自己、组长导出的只有本组，
      和列表看到的是同一批行（回归里有断言钉住这一点）。
    """
    q = _scoped_query(db, user, f)
    assert_export_size(q.count())
    rows = (
        q.order_by(AnnotationRecord.work_date.desc(), AnnotationRecord.id.desc())
        .all()
    )
    out = _enrich(db, rows)
    payload = [
        {
            "记录ID": r.id,
            "标注人": r.user_name,
            "项目": r.project_name,
            "日期": r.work_date.isoformat(),
            "条目号": r.item_no,
            "2D框数": r.box2d,
            "3D框数": r.box3d,
            "合计框数": r.box_total,
            "备注": r.remark,
            "是否被管理者修改": "是" if r.edited_by_manager else "",
            "填报时间": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        }
        for r in out
    ]
    return csv_response(
        payload,
        EXPORT_COLUMNS,
        f"标注记录_{today_cn().isoformat()}.csv",
        ascii_name="annotations.csv",
    )


# ————————————————————————————————————————————————
# 增
# ————————————————————————————————————————————————
@router.post("", response_model=AnnotationOut, status_code=201)
def create_annotation(
    body: AnnotationCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """登记一条标注。

    ★ **重复不拦**。同人 + 同项目 + 同天 + 同条目号**允许**存多条
      （真实场景里同一个条目号当天分几批做很常见），只把
      `suspected_duplicate` 置 true 让前端提示一句。
      所以重复时返回的是 **201**，不是 v1 那种 409。

    ★ 归属判定排在最前面（404 优先于一切 422），见 core/rules.py 里的说明。
    """
    owner_id, on_behalf = resolve_owner(db, user, body.user_id)
    assert_date_allowed(user, body.work_date)
    _check_project(db, body.project_id)

    dup = (
        db.query(AnnotationRecord.id)
        .filter(
            AnnotationRecord.user_id == owner_id,
            AnnotationRecord.project_id == body.project_id,
            AnnotationRecord.work_date == body.work_date,
            AnnotationRecord.item_no == body.item_no.strip(),
        )
        .first()
        is not None
    )

    r = AnnotationRecord(
        user_id=owner_id,
        project_id=body.project_id,
        work_date=body.work_date,
        item_no=body.item_no.strip(),
        box2d=body.box2d,
        box3d=body.box3d,
        remark=body.remark.strip(),
        edited_by_manager=on_behalf,
    )
    db.add(r)
    db.flush()
    if on_behalf:
        log_action(
            db,
            actor=user,
            action="代填标注数据",
            target_type="annotation",
            target_id=r.id,
            summary=(
                f"为 {body.work_date} 代填条目 {r.item_no or '（无）'}"
                f"：2D {body.box2d} / 3D {body.box3d}"
            ),
            detail={"after": _snapshot(r), "owner_id": owner_id},
            ip=client_ip(request),
        )
    db.commit()
    db.refresh(r)
    out = _enrich(db, [r])[0]
    out.suspected_duplicate = dup
    return out


# ————————————————————————————————————————————————
# 改
# ————————————————————————————————————————————————
@router.patch("/{rid}", response_model=AnnotationOut)
def update_annotation(
    rid: int,
    body: AnnotationUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """改一条标注。

    ★ 越权与「记录不存在」走**同一个 raise**，detail 逐字相同。
      这是本平台的铁律（v1 起写在 README 里）：403 等于承认「这条存在」，
      等于免费送一个存在性预言机。方言平台那边先查存在性再查权限，不要学。
    """
    r = db.get(AnnotationRecord, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    # 自己 → False（不留痕）；范围内他人 → True（留痕）；范围外 → 直接 404
    on_behalf = assert_can_touch(db, user, r.user_id)
    if not on_behalf:
        assert_date_allowed(user, r.work_date)

    before = _snapshot(r)
    if body.item_no is not None:
        r.item_no = body.item_no.strip()
    if body.box2d is not None:
        r.box2d = body.box2d
    if body.box3d is not None:
        r.box3d = body.box3d
    if body.remark is not None:
        r.remark = body.remark.strip()
    after = _snapshot(r)

    # 动了别人的记录才留痕。改自己的不算——否则每个人改自己的都被标成
    # 「被管理者修改」，这个标记立刻失去意义。
    if on_behalf and before != after:
        r.edited_by_manager = True
        log_action(
            db,
            actor=user,
            action="修改标注数据",
            target_type="annotation",
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
def delete_annotation(
    rid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(AnnotationRecord, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    on_behalf = assert_can_touch(db, user, r.user_id)
    if not on_behalf:
        assert_date_allowed(user, r.work_date)

    if on_behalf:
        log_action(
            db,
            actor=user,
            action="删除标注数据",
            target_type="annotation",
            target_id=r.id,
            summary=(
                f"记录 #{r.id}（{r.work_date}，条目 {r.item_no or '（无）'}，"
                f"合计 {r.box2d + r.box3d} 框）被管理者删除"
            ),
            detail={"before": _snapshot(r), "owner_id": r.user_id},
            ip=client_ip(request),
        )

    db.delete(r)
    db.commit()
    return {"ok": True}
