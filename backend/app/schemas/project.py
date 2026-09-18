from datetime import datetime

from pydantic import BaseModel, Field


# ★ 三个模型都**没有 `unit`**（v1 遗留字段，v2 起停用）。
#   列本身还在 `models/project.py` 里留着（`DROP COLUMN` 不可逆，而一个空列的
#   存续成本是零），但**接口层一个口子都不留**：v2 的数量口径是 2D/3D 框数，
#   单位恒为「框」。
#
#   留着入参的话，后台里会继续有人填「条 / 句 / 张」，而那些值不会被任何一处读取
#   ——填的人以为它有意义，看到的人以为它是真的。这类字段的害处不是浪费一次输入，
#   是让人对数据产生一个错误的预期。
#
#   ⚠️ pydantic 默认 `extra='ignore'`：**从入参删掉一个字段不会让传了它的请求报错**。
#   所以这一步不会自己暴露漏改的调用点，得靠 grep（或直接读一遍前端表单）。
class ProjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    # active / archived
    status: str | None = None


class ProjectOut(BaseModel):
    id: int
    code: str
    name: str
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
