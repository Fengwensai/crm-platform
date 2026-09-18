from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    status: str
    # 所属团队。`team_name` 由 routers/users.py 的 `_enrich_users` 批量补上，
    # 不是关系属性——否则渲染一页用户就是几十次 lazy load。
    team_id: int | None = None
    team_name: str = ""
    created_at: datetime | None = None
    reviewed_at: datetime | None = None
    review_note: str = ""


class UserOption(BaseModel):
    """下拉选项。**只给最小必要字段**。

    ★ 与 `UserOut` 分开而不是复用：`UserOut` 里有审批信息（status / review_note
      / reviewed_at）。下拉框不需要它们，而一旦共用一个模型，以后往 `UserOut`
      加任何字段都会**自动**出现在每个登录用户都能调的 `/api/users/options`
      响应里。泄露是这么发生的：不是有人故意加的，是有人忘了它俩是同一个模型。
    """

    id: int
    name: str
    username: str
    role: str = "employee"
    team_id: int | None = None
    team_name: str = ""


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    # 仅超管可改角色；管理者传 role 会被 403
    role: str | None = None
    # active（启用）/ disabled（停用）
    status: str | None = None
    # 重置密码（不传则不改）
    password: str | None = Field(default=None, min_length=6, max_length=128)
    # 调组。传 null = 移出团队。
    #
    # ★ 用 `model_fields_set` 区分「没传这个字段」和「传了 null」——只看值是否为
    #   None 的话，永远无法把一个人移出团队（传 null 会被当成「没传」而忽略）。
    team_id: int | None = None


class ReviewIn(BaseModel):
    """审批（通过/驳回）时可带备注，驳回时建议写明原因。"""

    note: str = Field(default="", max_length=255)
