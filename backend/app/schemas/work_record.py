from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class WorkRecordCreate(BaseModel):
    project_id: int
    work_date: date
    amount: int = Field(ge=0, le=10_000_000)
    rework_amount: int = Field(default=0, ge=0, le=10_000_000)
    remark: str = Field(default="", max_length=255)
    # 仅管理者生效：代某位员工补录。员工传这个字段会被服务端忽略
    # （永远只给自己填），不是靠前端不显示。
    user_id: int | None = None

    @model_validator(mode="after")
    def _check_rework(self):
        # 返工量是总量的子集，超过总量必然是填错了
        if self.rework_amount > self.amount:
            raise ValueError("返工量不能大于总量")
        return self


class WorkRecordUpdate(BaseModel):
    amount: int | None = Field(default=None, ge=0, le=10_000_000)
    rework_amount: int | None = Field(default=None, ge=0, le=10_000_000)
    remark: str | None = Field(default=None, max_length=255)


class WorkRecordOut(BaseModel):
    id: int
    user_id: int
    # 冗余展示字段：前端列表/管理者总览直接显示，省一次查询
    user_name: str = ""
    project_id: int
    project_name: str = ""
    unit: str = "条"
    work_date: date
    amount: int
    rework_amount: int
    # 合格量 = 总量 - 返工量
    qualified: int = 0
    remark: str = ""
    # 是否被管理者改动过（员工端会标出来）
    edited_by_manager: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
