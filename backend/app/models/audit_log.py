from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AuditLog(Base):
    """操作审计日志。核心用途：管理者修改/删除员工数据时留 before→after 快照。

    这是「共享表格不安全」的对症解法——表格里谁改了什么无人知晓，
    这里每一次越权（管理者动员工数据）都可追溯。
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(nullable=True)
    # 冗余快照，防止账号被删后日志失联（与方言平台同一做法）
    actor_name: Mapped[str] = mapped_column(String(64), default="")
    # 中文动词，如「修改工作数据」「删除工作数据」「审批通过」
    action: Mapped[str] = mapped_column(String(32), index=True)
    # work_record / user / project
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(String(512), default="")
    # 结构化信息：改动的 before / after 快照
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
