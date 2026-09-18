from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class User(Base):
    """统一账号表：超管 / 管理者 / 组长 / 员工 四种角色共用。

    员工走「自助注册 + 审批」：注册后 status=pending，管理员审批通过才置 active
    并可登录；未通过的一律登录不上（登录接口会拦 status != active）。

    注意：四种角色是同一张表靠 role 区分，不拆表——都要登录、都要 JWT，
    拆表只会让鉴权多一套分支，没有收益。

    ★ 组长 = `role == "leader"` **且** `team_id` 非空。两者必须同时成立：
      role 是「是不是组长」的唯一真相源（不设 Team.leader_id，那是双真相源）；
      team_id 是「管哪个组」。数据隔断的解析在 `core/scope.py`，
      其中「role=leader 但 team_id 为空」会解析成**空集**——配置失误绝不能
      退化成「看到全公司」。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 工号，登录名（员工注册时自填，管理员审批时核对）
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    # super_admin / manager / leader / employee
    role: Mapped[str] = mapped_column(String(20), default="employee", index=True)
    # 所属团队。管理者与超管不参与团队隔断，留空。普通成员留空表示「未分组」，
    # 此时只有他自己（以及管理者）能看到他的数据。
    team_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    # pending（待审批）/ active（正常）/ rejected（已驳回）/ disabled（已停用）
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # 审批留痕：谁批的、何时、备注（驳回时写原因）
    reviewed_by: Mapped[int | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str] = mapped_column(String(255), default="")
