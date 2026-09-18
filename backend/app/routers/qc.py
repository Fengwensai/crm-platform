"""质检工作量（双轨之二）。

一条质检记录 = 「被质检人员 + 条目号 + 通过/打回」。
与标注轨的结构约定完全一致（唯一查询入口 `_scoped_query`、scope 永远先盖），
但**可见性规则不同**，见下面这段。

————————————————————————————————————————————————————————————
★ 质检记录的可见性 = **并集**：「我检的」∪「被检人在我范围内的」

为什么不按被检人一头判（那样更直觉）：

    质检员给**别组**的人做了一条质检 → 保存成功 → 列表刷新 →
    **这条自己刚提交的记录不在列表里**。他既看不到，也改不了。

    这不是泄密，是**系统否认了他对自己提交数据的所有权**。用户不会想到
    「哦这是权限设计」，他只会认为「系统丢数据了」——然后重新填一遍，
    于是库里出现两条一样的记录，通过率被算进去两次。

    而跨组质检一定会有（已与用户确认：被质检人员下拉给全员）。

所以读写共用一个谓词 `visible_qc_filter`。单条接口写成
`filter(QcRecord.id == rid, visible_qc_filter(db, user))` ——
一条查询同时完成「存在性」与「权限」，`None` 就 404，
**物理上不给「取到了但忘了判权限」留空间**。
"""

from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.audit import log_action
from ..core.deps import get_current_user
from ..core.netutil import client_ip
from ..core.rules import assert_date_allowed
from ..core.scope import visible_qc_filter
from ..core.tz import today_cn
from ..db import get_db
from ..models.project import Project
from ..models.qc_record import QcRecord
from ..models.user import User
from ..schemas.qc import QcCreate, QcOut, QcPage, QcUpdate, PassRateOut
from ..services.export import assert_export_size, csv_response

router = APIRouter(prefix="/api/qc-records", tags=["质检"])

EXPORT_COLUMNS = [
    "记录ID",
    "质检人",
    "被质检人员",
    "项目",
    "日期",
    "条目号",
    "结论",
    "备注",
    "是否被管理者修改",
    "填报时间",
]

RESULT_LABELS = {"pass": "通过", "reject": "打回"}


# ————————————————————————————————————————————————
# 筛选条件：list 与 export 共用
# ————————————————————————————————————————————————
@dataclass
class QcFilters:
    date_from: date | None = None
    date_to: date | None = None
    project_id: int | None = None
    inspector_id: int | None = None
    target_user_id: int | None = None
    result: str | None = None


def qc_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = None,
    inspector_id: int | None = None,
    target_user_id: int | None = None,
    result: str | None = None,
) -> QcFilters:
    """两个筛选参数刻意**分开命名**（`inspector_id` / `target_user_id`），
    不叫笼统的 `user_id`。

    ★ 一张质检表上有两个「人」。一个叫 `user_id` 的参数必然要在某个时刻
      被某个人解释成另一端——而两种解释在代码上都说得通、都不报错，
      只是查出来的行完全不同。名字分不清，就一定会错。
    """
    return QcFilters(
        date_from=date_from,
        date_to=date_to,
        project_id=project_id,
        inspector_id=inspector_id,
        target_user_id=target_user_id,
        result=result,
    )


def _scoped_query(db: Session, user: User, f: QcFilters):
    # ★ 先盖可见性（并集），用户传的筛选只能在它之上收窄
    q = db.query(QcRecord).filter(visible_qc_filter(db, user))
    if f.inspector_id is not None:
        q = q.filter(QcRecord.inspector_id == f.inspector_id)
    if f.target_user_id is not None:
        q = q.filter(QcRecord.target_user_id == f.target_user_id)
    if f.project_id is not None:
        q = q.filter(QcRecord.project_id == f.project_id)
    if f.result is not None:
        q = q.filter(QcRecord.result == f.result)
    if f.date_from is not None:
        q = q.filter(QcRecord.qc_date >= f.date_from)
    if f.date_to is not None:
        q = q.filter(QcRecord.qc_date <= f.date_to)
    return q


def _enrich(db: Session, rows: list[QcRecord], me: User) -> list[QcOut]:
    if not rows:
        return []
    uids = {r.inspector_id for r in rows} | {r.target_user_id for r in rows}
    unames = dict(db.query(User.id, User.name).filter(User.id.in_(uids)).all())
    pnames = dict(
        db.query(Project.id, Project.name)
        .filter(Project.id.in_({r.project_id for r in rows}))
        .all()
    )
    return [
        QcOut(
            id=r.id,
            inspector_id=r.inspector_id,
            inspector_name=unames.get(r.inspector_id, ""),
            target_user_id=r.target_user_id,
            target_name=unames.get(r.target_user_id, ""),
            project_id=r.project_id,
            project_name=pnames.get(r.project_id, ""),
            qc_date=r.qc_date,
            item_no=r.item_no,
            result=r.result,
            remark=r.remark,
            edited_by_manager=r.edited_by_manager,
            mine=r.inspector_id == me.id,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def _snapshot(r: QcRecord) -> dict:
    return {
        "qc_date": r.qc_date.isoformat(),
        "item_no": r.item_no,
        "result": r.result,
        "remark": r.remark,
    }


def _check_project(db: Session, project_id: int) -> None:
    p = db.get(Project, project_id)
    if p is None or p.status != "active":
        raise HTTPException(status_code=422, detail="项目不存在或已归档")


# ————————————————————————————————————————————————
# 通过率（放在 /{rid} 之前声明，避免被路径参数吃掉）
# ————————————————————————————————————————————————
@router.get("/pass-rate", response_model=PassRateOut)
def pass_rate(
    project_id: int | None = None,
    item_no: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """该条目号的历史通过率——登记表单里那个「通过率（自动计算）」。

    ★ 分组键是 **`(project_id, item_no)`**，不是裸 `item_no`。

      条目号是**项目内**编号：项目 A 的 `123` 和项目 B 的 `123` 是两回事。
      只按 `item_no` 聚合会把两个项目混算出一个**既不是 A 也不是 B** 的数，
      而且它看起来完全正常。

      这个改法是**严格占优**的，所以当初没有取舍可问：若条目号本就全局唯一，
      加上 `project_id` 是恒等变换；若它是项目内编号，不加就是错的。

    ★ 刻意**不受数据范围限制**（不盖 scope）。通过率是**条目本身的属性**，
      不是「这个登录者能看到的那部分历史」。若盖了 scope，同一个条目号
      在组长和员工那里会显示成两个不同的百分比，那它就不再是「历史通过率」了。

    ★ 两键缺一或该条目没有任何历史 → `{total:0, passed:0, rejected:0, rate:0.0}`。
      「0 条 → 0.0」**只在服务端算**，见 schemas/qc.py 的说明。
    """
    if not project_id or not item_no:
        # 表单还没填全，前端会无条件调用——所以这里必须返回合法空值而不是 422，
        # 否则用户每敲一个字都会看到一次报错。
        return PassRateOut()

    row = (
        db.query(
            func.count(QcRecord.id),
            func.count(QcRecord.id).filter(QcRecord.result == "pass"),
        )
        .filter(
            QcRecord.project_id == project_id,
            QcRecord.item_no == item_no.strip(),
        )
        .one()
    )
    total, passed = int(row[0] or 0), int(row[1] or 0)
    rejected = total - passed
    # total 为 0 时**直接给 0.0**，不做除法——`0/0` 在 Python 里是 ZeroDivisionError，
    # 在 JS 里是 NaN，两边都会把页面显示成 `NaN%` 或直接 500。
    rate = round(passed / total, 4) if total else 0.0
    return PassRateOut(total=total, passed=passed, rejected=rejected, rate=rate)


# ————————————————————————————————————————————————
# 查
# ————————————————————————————————————————————————
@router.get("", response_model=QcPage)
def list_qc(
    f: QcFilters = Depends(qc_filters),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _scoped_query(db, user, f)
    total = q.count()
    rows = (
        q.order_by(QcRecord.qc_date.desc(), QcRecord.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return QcPage(items=_enrich(db, rows, user), total=total)


@router.get("/export")
def export_qc(
    f: QcFilters = Depends(qc_filters),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _scoped_query(db, user, f)
    assert_export_size(q.count())  # ★ 必须在 .all() 之前，见 services/export.py
    rows = (
        q.order_by(QcRecord.qc_date.desc(), QcRecord.id.desc()).all()
    )
    payload = [
        {
            "记录ID": r.id,
            "质检人": r.inspector_name,
            "被质检人员": r.target_name,
            "项目": r.project_name,
            "日期": r.qc_date.isoformat(),
            "条目号": r.item_no,
            "结论": RESULT_LABELS.get(r.result, r.result),
            "备注": r.remark,
            "是否被管理者修改": "是" if r.edited_by_manager else "",
            "填报时间": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        }
        for r in _enrich(db, rows, user)
    ]
    return csv_response(
        payload,
        EXPORT_COLUMNS,
        f"质检记录_{today_cn().isoformat()}.csv",
        ascii_name="qc_records.csv",
    )


# ————————————————————————————————————————————————
# 增
# ————————————————————————————————————————————————
@router.post("", response_model=QcOut, status_code=201)
def create_qc(
    body: QcCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """登记一条质检。

    ★ **质检人恒为登录者自己**，不接受任何形式的「代填」。
      质检是「我看了这份活」的声明，让别人以你的名义署上去，等于伪造工作记录。
      （这与标注轨不同：那边组长代组员补录数量是正当的，因为记录的内容是
      客观的框数；而质检记录的**内容就是作者本人**。）

    ★ 被质检人员**不限范围**（全员可选，已与用户确认）。但必须真实存在，
      且**不能是自己**——自己质检自己在业务上无意义，还会把通过率刷成 100%。

    ★ 顺序：先判目标是否存在（404），再判是不是自己（422）。
      范围检查必须早于一切因数据内容而异的校验，否则就成了存在性预言机。
    """
    target = db.get(User, body.target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="指定的员工不存在")
    if target.id == user.id:
        raise HTTPException(status_code=422, detail="不能质检自己")

    assert_date_allowed(user, body.qc_date)
    _check_project(db, body.project_id)

    r = QcRecord(
        inspector_id=user.id,
        target_user_id=target.id,
        project_id=body.project_id,
        qc_date=body.qc_date,
        item_no=body.item_no.strip(),
        result=body.result,
        remark=body.remark.strip(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _enrich(db, [r], user)[0]


# ————————————————————————————————————————————————
# 改
# ————————————————————————————————————————————————
@router.patch("/{rid}", response_model=QcOut)
def update_qc(
    rid: int,
    body: QcUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """改一条质检。

    ★★ 本文件最容易写错的一行在下面那句 `r.inspector_id == user.id`。

      写成 `target_user_id` 的话：「组长给自己组员录一条质检，再编辑它」，
      记录作者明明是他自己，却会被标上「已被管理者修改」。
      这个 bug **只在「组长/管理者兼任质检员」时现形**——
      而兼职质检恰恰是这个平台最可能的真实用法，也恰恰是最容易漏测的组合。
      （回归里有一条专门钉它：`verify_core` 的「给自己组员录质检再编辑不应留痕」。）
    """
    r = (
        db.query(QcRecord)
        .filter(QcRecord.id == rid, visible_qc_filter(db, user))
        .first()
    )
    if r is None:
        # 不存在 / 越权 / 别组的记录 —— 全部走这一句，detail 逐字相同。
        # 一条查询同时完成「存在性」与「权限」，没有「取到了但忘了判权限」的空间。
        raise HTTPException(status_code=404, detail="记录不存在")

    mine = r.inspector_id == user.id
    if mine:
        assert_date_allowed(user, r.qc_date)

    before = _snapshot(r)
    if body.item_no is not None:
        r.item_no = body.item_no.strip()
    if body.result is not None:
        r.result = body.result
    if body.remark is not None:
        r.remark = body.remark.strip()
    after = _snapshot(r)

    if not mine and before != after:
        r.edited_by_manager = True
        log_action(
            db,
            actor=user,
            action="修改质检数据",
            target_type="qc_record",
            target_id=r.id,
            summary=f"记录 #{r.id}（{r.qc_date}）{before} → {after}",
            detail={"before": before, "after": after, "inspector_id": r.inspector_id},
            ip=client_ip(request),
        )

    db.commit()
    db.refresh(r)
    return _enrich(db, [r], user)[0]


# ————————————————————————————————————————————————
# 删
# ————————————————————————————————————————————————
@router.delete("/{rid}")
def delete_qc(
    rid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = (
        db.query(QcRecord)
        .filter(QcRecord.id == rid, visible_qc_filter(db, user))
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="记录不存在")

    mine = r.inspector_id == user.id  # ★ 同上：作者，不是对象
    if mine:
        assert_date_allowed(user, r.qc_date)

    if not mine:
        log_action(
            db,
            actor=user,
            action="删除质检数据",
            target_type="qc_record",
            target_id=r.id,
            summary=(
                f"记录 #{r.id}（{r.qc_date}，条目 {r.item_no or '（无）'}，"
                f"{RESULT_LABELS.get(r.result, r.result)}）被管理者删除"
            ),
            detail={"before": _snapshot(r), "inspector_id": r.inspector_id},
            ip=client_ip(request),
        )

    db.delete(r)
    db.commit()
    return {"ok": True}
