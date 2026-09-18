"""集中导入所有模型：create_all 依赖这里把它们注册到 Base.metadata。

★ `WorkRecord` 是 v1 遗留（已停用），但**必须留在这里**——否则 `create_all`
  在新环境少建 `work_records` 表，线上与 CI/新机器的 schema 就漂了。
"""

from .annotation_record import AnnotationRecord
from .audit_log import AuditLog
from .project import Project
from .qc_record import QcRecord
from .team import Team
from .user import User
from .work_record import WorkRecord

__all__ = [
    "AnnotationRecord",
    "AuditLog",
    "Project",
    "QcRecord",
    "Team",
    "User",
    "WorkRecord",
]
