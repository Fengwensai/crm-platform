from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Project(Base):
    """项目：管理员建，员工登记时选择。

    ★ `unit` 是 **v1 遗留，v2 起停用**：v2 的数量口径是 2D/3D 框数，单位恒为「框」，
      这一列退化成了常量，而且有害——导出表头会写成「3D分割（条）」，框数写着「条」。
      v2 已从 `schemas/project.py`、建/改项目入参、前端表单和展示里**全部移除**。
      列本身保留不删：`DROP COLUMN` 不可逆，而留着它的成本是零。
      新代码**不要读写它**。
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    unit: Mapped[str] = mapped_column(String(16), default="条")  # v1 遗留，停用，见类注释
    # active（进行中，可填报）/ archived（已归档，不再出现在填报选项里）
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
