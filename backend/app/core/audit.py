from ..models.audit_log import AuditLog
from ..models.user import User


def log_action(
    db,
    *,
    actor: User | None,
    action: str,
    target_type: str = "",
    target_id: int | str | None = None,
    summary: str = "",
    detail: dict | None = None,
    ip: str = "",
) -> None:
    """写一条审计日志（只 add 不 commit，由调用方与业务改动同一事务提交）。

    actor 允许为 None（系统操作）；actor_name 冗余快照，防止账号被删后日志失联。
    """
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_name=(actor.name or actor.username) if actor else "",
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            summary=summary[:512],
            detail=detail or {},
            ip=ip,
        )
    )
