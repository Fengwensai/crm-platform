"""删除前的「有没有历史数据」检查。

————————————————————————————————————————————————————————————
为什么这个模块必须存在，而且要单独存在？

删账号 / 删项目的守卫，存在的唯一意义是**防止历史数据变成孤儿**
（README 里「共享表格是谁改了什么无人知晓」的同一条思路：数据不能凭空消失）。
漏改的后果**不是报错，而是「删除成功」**——超管点一下删除，那个人名下所有
标注和质检记录当场失去归属，界面上再也不会出现，且没有任何提示。
这类故障在测试里表现为「一切正常」，只有翻数据库才发现多了几百条 user_id 指向空。

所以：
  ★ 双轨（标注 + 质检）**两张表都要查**，质检表还要**两列都查**
    （他可能是被质检的人，也可能是做质检的人）。
  ★ v1 旧表 `work_records` 也留着一起查。它不是死数据——`migrate_v2.py` 明确
    保留了它供对账，把它排除在守卫外等于让这份对账底稿可以被删成孤儿。
    代价是一次 COUNT，收益是「宁可多拦，不可漏放」。
  ★ 判定做成「各表分别计数」而不是一个合计数字：管理员看到「已有 3 条记录」
    没法判断该去哪个页面核实，看到「标注 2 条 / 质检 1 条」才能。
"""

from sqlalchemy.orm import Session

from ..models.annotation_record import AnnotationRecord
from ..models.qc_record import QcRecord
from ..models.work_record import WorkRecord


def count_user_records(db: Session, uid: int) -> dict[str, int]:
    """这个账号名下的历史数据，按来源分类计数（值为 0 的项不返回）。"""
    counts = {
        "标注": db.query(AnnotationRecord.id)
        .filter(AnnotationRecord.user_id == uid)
        .count(),
        "质检": db.query(QcRecord.id).filter(QcRecord.inspector_id == uid).count(),
        "被质检": db.query(QcRecord.id)
        .filter(QcRecord.target_user_id == uid)
        .count(),
        "v1 填报": db.query(WorkRecord.id).filter(WorkRecord.user_id == uid).count(),
    }
    return {k: v for k, v in counts.items() if v}


def count_project_records(db: Session, pid: int) -> dict[str, int]:
    """这个项目名下的历史数据，按来源分类计数（值为 0 的项不返回）。"""
    counts = {
        "标注": db.query(AnnotationRecord.id)
        .filter(AnnotationRecord.project_id == pid)
        .count(),
        "质检": db.query(QcRecord.id).filter(QcRecord.project_id == pid).count(),
        "v1 填报": db.query(WorkRecord.id)
        .filter(WorkRecord.project_id == pid)
        .count(),
    }
    return {k: v for k, v in counts.items() if v}


def format_counts(counts: dict[str, int]) -> str:
    """把 {'标注': 2, '质检': 1} 说成人话：'标注 2 条、质检 1 条'。"""
    return "、".join(f"{k} {v} 条" for k, v in counts.items())
