from datetime import date

from pydantic import BaseModel

# ————————————————————————————————————————————————————————————————
# ★ 关于字段命名，这个文件有一条硬规矩：**双轨永不合并成一个「总产出」数字**。
#
#   框数（标注）和条数（质检）是不同量纲，相加没有意义。把它们塞进一个
#   `total` 字段，看板上会出现一个既不是框也不是条的怪数，而且它看起来很正常。
#
# ★ 另一条：v1 的 `total_rework` / `total_qualified` / `pass_rate` 三个字段名
#   **直接删掉，不保留成 0**。
#
#   v1 的 `pass_rate` = 合格量 / 总量（标注口径）；v2 的通过率 = 质检通过 / 质检总数
#   （质检口径）。同名不同义。留着的话，任何一处漏改的前端会显示一个
#   **错得看不出来**的百分比——数值量级完全在合理范围内，没人会怀疑它。
#   宁可让前端因为字段缺失当场报错，也不要让一个错数字静静地显示出来。
# ————————————————————————————————————————————————————————————————


class OverviewOut(BaseModel):
    """概览卡。双轨并列，不合并。"""

    # —— 标注轨 ——
    total_box2d: int = 0
    total_box3d: int = 0
    # = total_box2d + total_box3d
    total_box: int = 0
    annotation_count: int = 0
    # —— 质检轨 ——
    qc_total: int = 0
    qc_pass: int = 0
    qc_reject: int = 0
    # 质检通过率 = qc_pass / qc_total；无质检记录时为 0.0
    qc_pass_rate: float = 0.0
    # —— 人员与项目 ——
    # 这些计数同样受调用者的数据范围约束：管理者看到的是全公司，
    # 组长看到的是本组，员工看到的是 1（他自己）。
    employee_count: int = 0
    active_employee_count: int = 0
    project_count: int = 0
    # 待审批账号数（顶栏红点）。★ 仅管理者拿到真值；非管理者恒为 0，
    # 因为「有几个账号在等审批」是管理信息，不该通过一个谁都能调的接口漏出去。
    pending_count: int = 0
    # 这份数字的范围，由服务端算好给前端直接显示（「本人 / 本组全量 / 全公司」）。
    # 放服务端是因为范围本来就是服务端定的，前端再推一遍等于把同一个判断写两处。
    scope_label: str = ""


class TrendPoint(BaseModel):
    """一天。两条轨共用同一个日期轴。"""

    work_date: date
    # 标注轨
    box2d: int = 0
    box3d: int = 0
    box_total: int = 0
    # 质检轨
    qc_total: int = 0
    qc_pass: int = 0
    qc_reject: int = 0


class TrendOut(BaseModel):
    points: list[TrendPoint] = []
    # 窗口内合计，前端画标题用
    total_box2d: int = 0
    total_box3d: int = 0
    total_box: int = 0
    qc_total: int = 0
    qc_pass: int = 0
    qc_reject: int = 0


class ByUserRow(BaseModel):
    """按人聚合。

    ★★ 两个通过率是**方向相反的两件事**，必须是两个独立字段：

      · `qc_as_inspector_pass_rate` —— 他做质检时的通过率（**他判别人**，
        高 = 他手松；偏低 = 他比较严格）
      · `qc_as_target_pass_rate`    —— 他被质检时的通过率（**别人判他**，
        这才是通常意义上「他的质量」）

      用一个词（比如 `pass_rate`）指代它们中的任何一个，迟早会被另一处当成
      另一个用。两个数都合理、都不报错，只是意思正好相反。
    """

    user_id: int
    name: str = ""
    username: str = ""
    # —— 标注轨 ——
    box2d: int = 0
    box3d: int = 0
    box_total: int = 0
    annotation_count: int = 0
    # 有标注记录的天数
    days: int = 0
    # —— 质检轨：他做质检 ——
    qc_as_inspector_total: int = 0
    qc_as_inspector_pass: int = 0
    qc_as_inspector_pass_rate: float = 0.0
    # —— 质检轨：他被质检 ——
    qc_as_target_total: int = 0
    qc_as_target_pass: int = 0
    qc_as_target_pass_rate: float = 0.0


class ByProjectRow(BaseModel):
    project_id: int
    code: str = ""
    name: str = ""
    # —— 标注轨 ——
    box2d: int = 0
    box3d: int = 0
    box_total: int = 0
    annotation_count: int = 0
    # 参与该项目标注的人数
    people: int = 0
    # —— 质检轨 ——
    qc_total: int = 0
    qc_pass: int = 0
    qc_reject: int = 0
    qc_pass_rate: float = 0.0


class AnnotationSummaryOut(BaseModel):
    """标注记录页顶部的统计卡。

    ★ 卡片**只受数据范围约束，不受筛选条约束**——设计稿把卡片放在筛选条上面，
      而「今日工作量」配上「开始日期 = 上个月」本来就是自相矛盾的组合。
      所以这个接口不接受任何日期/项目参数。
    """

    today_people: int = 0
    today_box: int = 0
    total_box: int = 0
    people: int = 0
    scope_label: str = ""


class QcSummaryOut(BaseModel):
    """质检记录页顶部的统计卡（同样不受筛选条约束）。"""

    total: int = 0
    passed: int = 0
    rejected: int = 0
    scope_label: str = ""
