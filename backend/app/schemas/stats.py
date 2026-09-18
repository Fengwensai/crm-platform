from datetime import date

from pydantic import BaseModel


class OverviewOut(BaseModel):
    """管理者总览卡。"""

    total_amount: int = 0
    total_rework: int = 0
    total_qualified: int = 0
    # 合格率 = 合格量 / 总量（无数据时为 0）
    pass_rate: float = 0.0
    record_count: int = 0
    employee_count: int = 0
    active_employee_count: int = 0
    project_count: int = 0
    # 待审批账号数（顶栏红点）
    pending_count: int = 0


class TrendPoint(BaseModel):
    work_date: date
    amount: int = 0
    rework: int = 0
    qualified: int = 0


class TrendOut(BaseModel):
    points: list[TrendPoint] = []
    # 窗口内合计，前端画标题用
    total_amount: int = 0
    total_rework: int = 0


class ByUserRow(BaseModel):
    user_id: int
    name: str = ""
    username: str = ""
    amount: int = 0
    rework: int = 0
    qualified: int = 0
    pass_rate: float = 0.0
    # 有填报记录的天数
    days: int = 0


class ByProjectRow(BaseModel):
    project_id: int
    code: str = ""
    name: str = ""
    unit: str = "条"
    amount: int = 0
    rework: int = 0
    qualified: int = 0
    pass_rate: float = 0.0
    # 参与该项目填报的人数
    people: int = 0


class MyStatsOut(BaseModel):
    """员工端「我的统计」。"""

    total_amount: int = 0
    total_rework: int = 0
    total_qualified: int = 0
    pass_rate: float = 0.0
    days: int = 0
    trend: list[TrendPoint] = []
    by_project: list[ByProjectRow] = []
