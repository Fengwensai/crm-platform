from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Team(Base):
    """团队（分组）。成员靠 `User.team_id` 归属。

    **故意不设 `leader_id` 字段。** 组长是谁由 `User.role == "leader"` 唯一决定，
    两者并存就是双真相源：在用户管理页把某人降级为 employee 而忘了改 leader_id 时，
    「他到底是不是组长」就没有唯一答案了，而且两边都不会报错。
    团队列表接口需要展示组长名字时**派生**一个字段即可，不参与任何权限判定。

    用表而不是 `User.team_name` 字符串：组名要能改（改一次得 UPDATE 全组行）、
    组要能列出来（字符串存法只能 SELECT DISTINCT）、而且打错一个字就凭空多出一个组，
    「本组」判定按字符串相等会**静默失效**，组长忽然看不见自己的组员。
    """

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # active（正常）/ archived（已归档，不出现在「分配成员」下拉里，历史记录完好）
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
