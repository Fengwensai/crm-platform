from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AnnotationRecord(Base):
    """标注工作量：某员工在某项目某天对某个条目号的标注产出。

    取代 v1 的 `WorkRecord`（数量 + 返工量）。现在的口径是框数：
    **工作量 = box2d + box3d**（设计稿里的「总工作量」就是这么加出来的）。

    ★ **故意不设唯一约束**（用户确认的规则）：同人 + 同项目 + 同天 + 同条目号
      允许有多条——同一条目号可能分多次、多班次登记。重复只提示不拦，
      提示走 `suspected_duplicate` 布尔字段（服务端算），不是数据库约束。

    ★ `item_no` 是**字符串不是整数**：标注条目号会出现 `007`、`A-001`、`12-3`
      这类形态。存整数会让 `007` 和 `7` 塌缩成同一行，而 `item_no` 正是质检
      通过率的聚合键——塌缩之后通过率会算错，**而且不会有任何报错**。
    """

    __tablename__ = "annotation_records"
    __table_args__ = (
        # 专供「疑似重复」探测的非唯一索引（不是唯一约束，重复是合法的）
        Index("ix_anno_dup_probe", "user_id", "project_id", "work_date", "item_no"),
        Index("ix_anno_user_date", "user_id", "work_date"),
        Index("ix_anno_project_date", "project_id", "work_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    item_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    # 2D / 3D 框数；工作量 = 两者之和
    box2d: Mapped[int] = mapped_column(Integer, default=0)
    box3d: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 最近一次被「非本人」改动（组长/管理者），供前端标「已被管理者修改」
    edited_by_manager: Mapped[bool] = mapped_column(default=False)
