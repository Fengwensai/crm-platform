from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Project(Base):
    """项目：管理员建，员工填报时选择。

    unit 是「数量」的单位（条 / 张 / 个…），仅用于展示与导出表头，
    不参与计算——不同项目单位不同，但统计时都是纯数字相加。
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    unit: Mapped[str] = mapped_column(String(16), default="条")
    # active（进行中，可填报）/ archived（已归档，不再出现在填报选项里）
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
