from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_manager
from ..core.scope import resolve_scope, visible_qc_filter
from ..db import get_db
from ..models.annotation_record import AnnotationRecord
from ..models.audit_log import AuditLog
from ..models.qc_record import QcRecord
from ..models.user import User
from ..schemas.audit import AuditLogOut

router = APIRouter(prefix="/api/audit-logs", tags=["审计日志"])

# 「这条记录的历史」支持的对象类型 → 该类型下「谁看得见这条记录」的判定。
# ★ 加新表时**必须**在这里加一条，否则那条记录上的「已修改」标记点开会 422
#   （fail-closed，是安全的方向），而不是默默泄露别人记录的历史。
_OWNED_TYPES = ("annotation", "qc_record")


@router.get("", response_model=list[AuditLogOut])
def list_logs(
    action: str | None = None,
    actor_id: int | None = None,
    target_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """审计日志（仅管理者可见）。重点看「修改工作数据 / 删除工作数据 / 代填」——
    管理者动员工数据的每一次都在这，含 before → after 快照。"""
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor_id is not None:
        q = q.filter(AuditLog.actor_id == actor_id)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if date_from is not None:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        # 含当天：+1 天再用 < 比较
        q = q.filter(AuditLog.created_at < date_to + timedelta(days=1))
    return q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()


# ★ 路由声明顺序：`""` 在前、`/mine` 在后。当前两者都是字面量路径，不会互相吃掉；
#   但哪天要加 `/{rid}` 这类路径参数，必须把它排到最后，否则 `/mine` 会被
#   当成 `rid` 匹配走（表现为「这个接口返回 404 / 422 记录 ID 不合法」）。
@router.get("/mine", response_model=list[AuditLogOut])
def my_record_logs(
    target_type: str,
    target_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """**某一条记录**的修改历史，给被改动的人自己看。

    ★ 这是 README 开篇那句「共享表格的问题是谁改了什么无人知晓」的正解：
      不是把日志攒起来给管理者看，而是**让被改的人自己看见**。
      记录行上那个「已被管理者修改」标记点开来的就是这个接口。

    ★ 权限判定**复用记录本体的可见性谓词**，不另写一套：
      · annotation → `resolve_scope(...).on(AnnotationRecord.user_id)`
      · qc_record  → `visible_qc_filter(...)`（「我检的」∪「被检人在我范围内的」）

      另写一套的话，两处迟早不一致，而不一致的方向必然是**更松**的那一边
      ——因为松的一边不报错。判定不过一律 404（本平台的铁律，见 README 规则表）。

    ★ `target_type` 不在白名单里 → **422 fail-closed**，不是「返回空列表」。
      返回空列表看起来和「这条没被改过」一模一样，而实际是「我不认识这种类型」。
    """
    if target_type not in _OWNED_TYPES:
        raise HTTPException(status_code=422, detail="不支持的记录类型")

    if target_type == "annotation":
        visible = (
            db.query(AnnotationRecord.id)
            .filter(
                AnnotationRecord.id == target_id,
                resolve_scope(db, user).on(AnnotationRecord.user_id),
            )
            .first()
            is not None
        )
    else:
        visible = (
            db.query(QcRecord.id)
            .filter(QcRecord.id == target_id, visible_qc_filter(db, user))
            .first()
            is not None
        )
    if not visible:
        # 不存在 / 越权 —— 同一句 detail，与记录接口逐字相同
        raise HTTPException(status_code=404, detail="记录不存在")

    return (
        db.query(AuditLog)
        .filter(AuditLog.target_type == target_type, AuditLog.target_id == str(target_id))
        # ★ 正序：要读成「先改成 A，再改成 B」。倒序的话用户会把因果读反。
        .order_by(AuditLog.id.asc())
        .all()
    )
