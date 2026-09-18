from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class QcRecord(Base):
    """质检工作量：一条质检记录 = 一个条目号。

    表上有**两个**人，别搞混：
    - `inspector_id`   质检人（谁做的这次质检，也就是提交人）
    - `target_user_id` 被质检人员（被检的是谁）—— 列表/筛选/表格都围绕他组织

    ★ 归属判定（见 `routers/qc_records.py` 的 `_qc_visible`）取**并集**：
      「我检的」∪「被检人在我范围内的」。只按被检人判的话，质检员给别组的人
      做了一条质检、保存成功后刷新，**这条自己刚提交的记录不在列表里**——
      系统否认了他对自己提交数据的所有权，他会以为系统丢数据了。

    ★ `result` 用**字符串不用 bool**：本仓 `User.role`/`status`、`Project.status`、
      `AuditLog.action` 全是「短字符串 + 注释列值域」，bool 是唯一的例外；
      而且 bool 加不出第三态，将来出现「作废」「部分通过」时只能改表。
      值域 `pass` / `reject`，由 pydantic 的 `Literal` 兜住拼写。
    """

    __tablename__ = "qc_records"
    __table_args__ = (
        Index("ix_qc_target_date", "target_user_id", "qc_date"),
        Index("ix_qc_inspector_date", "inspector_id", "qc_date"),
        # 通过率专用：(项目, 条目号) 聚合——条目号是项目内编号，
        # 项目 A 的 123 和项目 B 的 123 是两回事，不能混算
        Index("ix_qc_project_item", "project_id", "item_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inspector_id: Mapped[int] = mapped_column(index=True)
    target_user_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(index=True)
    qc_date: Mapped[date] = mapped_column(Date, index=True)
    item_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    # pass（通过）/ reject（打回）
    result: Mapped[str] = mapped_column(String(10), index=True)
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # ★ 留痕判定必须用 inspector_id（提交人），不是 target_user_id：
    #   用被检人判的话，组长给自己组员录一条质检再编辑它，会被标成
    #   「被管理者修改」——可记录作者明明就是他自己。
    edited_by_manager: Mapped[bool] = mapped_column(default=False)
