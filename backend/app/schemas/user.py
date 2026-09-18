from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    status: str
    created_at: datetime | None = None
    reviewed_at: datetime | None = None
    review_note: str = ""

    model_config = {"from_attributes": True}


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    # 仅超管可改角色；管理者传 role 会被 403
    role: str | None = None
    # active（启用）/ disabled（停用）
    status: str | None = None
    # 重置密码（不传则不改）
    password: str | None = Field(default=None, min_length=6, max_length=128)


class ReviewIn(BaseModel):
    """审批（通过/驳回）时可带备注，驳回时建议写明原因。"""

    note: str = Field(default="", max_length=255)
