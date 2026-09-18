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
    """★ v1 遗留，v2 起**已停用**。

    v1 的口径是「标注量 + 返工量」单轨；v2 拆成双轨——数量部分进了
    `AnnotationRecord`（2D/3D 框数），质量部分进了 `QcRecord`（质检通过/打回）。

    保留原因：线上 `work_records` 表里还有一条 v1 时期的历史记录，
    `DROP TABLE` 不可逆，而留着这张表的成本是零。

    ★ **这个模型必须继续留在 `models/__init__.py` 里。** 否则 `create_all`
      会在新环境（CI、新机器）少建这张表，线上与它们的 schema 就漂了——
      而 CI 永远测不出线上的差异。

    新代码不要 import 它。将来真要清理，单独出一个脚本，别混在业务改造里。
    """

    __tablename__ = "work_records"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "work_date", name="uq_work_record_daily"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    rework_amount: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    edited_by_manager: Mapped[bool] = mapped_column(default=False)
