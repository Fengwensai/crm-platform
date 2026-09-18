from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class WorkRecord(Base):
    """工作数据（核心表）：某员工在某项目某天的标注量。

    唯一约束 uq_work_record_daily：同一人 + 同一项目 + 同一天只能有一条，
    重复提交在数据库层就被拦掉（应用层会先查给出友好提示，这里是兜底）。

    rework_amount 是「返工/不合格量」，是 amount 的子集（不是额外增量），
    合格量 = amount - rework_amount。
    """

    __tablename__ = "work_records"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "work_date", name="uq_work_record_daily"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    # 标注总量
    amount: Mapped[int] = mapped_column(Integer, default=0)
    # 返工/不合格量（amount 的子集）
    rework_amount: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 最近一次被管理者改动（员工自己改不算），供前端标「已被管理者修改」
    edited_by_manager: Mapped[bool] = mapped_column(default=False)
