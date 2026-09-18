from datetime import datetime

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    remark: str = Field(default="", max_length=255)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    # active（正常）/ archived（归档）
    status: str | None = None
    remark: str | None = Field(default=None, max_length=255)


class TeamOut(BaseModel):
    id: int
    name: str
    status: str = "active"
    remark: str = ""
    member_count: int = 0
    # ★ 派生的展示字段，**不参与任何权限判定**。
    #   权限的唯一真相源是 `User.role == "leader"`（见 models/team.py 的说明）。
    #   这两人不一致时（比如管理员把组长降级为员工），以 User.role 为准——
    #   这里显示的只是「组里现在挂着谁」，不是「谁能看这个组的数据」。
    leader_id: int | None = None
    leader_name: str = ""
    created_at: datetime | None = None
