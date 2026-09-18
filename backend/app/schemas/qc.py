from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# 质检结论。
# ★ 用 `Literal` 而不是裸 `str`：拼错的 'passed' / 'reject ' 会被 pydantic 挡在 422，
#   而不是悄悄存进库里，变成一个永远统计不到的结论——那种错不报任何警，
#   只表现为「通过率算出来偏低」，没人查得出来。
# ★ 用字符串而不是 bool：库里的 User.role/status、Project.status、AuditLog.action
#   全是「短字符串 + 注释标值域」，bool 是唯一的例外。而且 bool 加不出第三态，
#   而「作废」「部分通过」这类状态迟早会出现。
QcResult = Literal["pass", "reject"]


class QcCreate(BaseModel):
    # ★ 被质检人员：**全员可选**，不受登录者的数据范围限制。
    #   员工之间互相质检是常态，跨组质检也一定会有；若按范围限制，
    #   员工的下拉里只剩他自己，而「不能质检自己」又拦掉那条 —— 整个页面填不出东西。
    target_user_id: int
    project_id: int
    qc_date: date
    item_no: str = Field(default="", max_length=64)
    result: QcResult
    remark: str = Field(default="", max_length=255)


class QcUpdate(BaseModel):
    """改质检记录。

    ★ 不含 `inspector_id` / `target_user_id` / `project_id` / `qc_date`：
      前两个是**归属**（改了等于把这条工作记到别人头上），后两个是聚合键
      （通过率按 `project_id + item_no` 分组，改了它就等于改写了历史统计口径）。
      真要纠正归属，正确做法是删掉重建——那是一步显式操作，会留两条审计。
    """
    item_no: str | None = Field(default=None, max_length=64)
    result: QcResult | None = None
    remark: str | None = Field(default=None, max_length=255)


class QcOut(BaseModel):
    id: int
    # 质检人 = 这条记录的**作者**
    inspector_id: int
    inspector_name: str = ""
    # 被质检人 = 这条记录的**对象**。
    # ★ 两个名字必须分开叫。用一个含糊的 `user_name` 指代它们，
    #   前端总有一天会把「谁检的」显示成「检了谁」——而且是对称的，
    #   看的人不会觉得哪里不对。
    target_user_id: int
    target_name: str = ""
    project_id: int
    project_name: str = ""
    qc_date: date
    item_no: str = ""
    result: str = "pass"
    remark: str = ""
    # 是否被管理者改动过。
    # ★ 判定依据必须是 `inspector_id`（作者），不是 `target_user_id`（对象）。
    edited_by_manager: bool = False
    # 这条是不是「我提交的」。列表是并集（我检的 ∪ 被检人在我范围内的），
    # 两种来源混在一起，前端据此标一列「我检的 / 被检的」把混合语义显式化。
    mine: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QcPage(BaseModel):
    items: list[QcOut]
    total: int


class PassRateOut(BaseModel):
    """某个条目号的历史通过率。

    空表单（没有任何历史）返回 `total=0, rate=0.0`——**不是 None**。
    「0 条 → 0.0」这条规则**只在服务端算**，前端不做 `total ? x : 0`：
    那种写法每个调用点都要记得写一次，漏一个就显示成 `NaN%`。
    """
    total: int = 0
    passed: int = 0
    rejected: int = 0
    rate: float = 0.0
