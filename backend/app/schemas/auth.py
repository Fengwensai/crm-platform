from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    # 工号：登录名
    username: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    """`/api/auth/me`：前端据它决定整张菜单和每个页面的范围小字。

    ★ `team_id` 必须给。前端要据它区分「组长」和「**没挂组的**组长」——
      后者后端给他的是空集（他登录后什么都看不见），界面若不把这件事说出来，
      他只会认为系统坏了。`team_name` 一并给，用于顶栏显示「张三（甲组）」。
    """

    id: int
    username: str
    name: str
    role: str
    status: str
    team_id: int | None = None
    team_name: str = ""
    # 只读演示账号。前端据它置灰写操作入口并挂一条提示——
    # **只是 UX**，真正的拦截在服务端（core/deps.py:reject_readonly_write）。
    is_readonly: bool = False

    model_config = {"from_attributes": True}
