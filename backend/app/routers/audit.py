from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.deps import require_manager
from ..db import get_db
from ..models.audit_log import AuditLog
from ..models.user import User
from ..schemas.audit import AuditLogOut

router = APIRouter(prefix="/api/audit-logs", tags=["审计日志"])


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
