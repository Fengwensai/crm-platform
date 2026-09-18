from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class User(Base):
    """统一账号表：超管 / 管理者 / 员工 三种角色共用。

    员工走「自助注册 + 审批」：注册后 status=pending，管理员审批通过才置 active
    并可登录；未通过的一律登录不上（登录接口会拦 status != active）。

    注意：员工与管理者是同一张表靠 role 区分，不拆表——三者都要登录、都要
    JWT，拆表只会让鉴权多一套分支，没有收益。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 工号，登录名（员工注册时自填，管理员审批时核对）
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    # super_admin / manager / employee
    role: Mapped[str] = mapped_column(String(20), default="employee", index=True)
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
