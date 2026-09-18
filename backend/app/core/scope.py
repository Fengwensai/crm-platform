"""数据隔断：把「当前登录者是谁」翻译成「他能看到 / 能改哪些人的数据」。

**这是整个平台最该被记住的一个模块。** 需求②「数据隔断」的全部实现都收在这里，
而不是散落在各个 router 里。核心原则：

    ★ 可见性只有**一处**定义。读（列表的 SQL 过滤）和写（单条的 404 判定）
      都从同一个谓词派生，所以**物理上不可能**出现「能看不能改」或更糟的
      「列表过滤对了但单条忘了判」。

角色与范围：

| role        | 范围                                   |
|-------------|----------------------------------------|
| super_admin | 全部                                   |
| manager     | 全部                                   |
| leader      | 本组（`team_id` 相同的所有人）           |
| employee    | 只有自己                               |

★ **失败方向永远偏向锁死**：组长配置失误（`role='leader'` 但没挂组）解析成**空集**，
  未知 role 值降级成「只有自己」。绝不允许任何一条分支在信息不全时放行成全量。
"""

from fastapi import HTTPException
from sqlalchemy import Select, or_, select, true
from sqlalchemy.orm import Session

from ..models.user import User

MANAGER_ROLES = ("manager", "super_admin")
LEADER_ROLE = "leader"
ALL_ROLES = ("employee", "leader", "manager", "super_admin")

# 「组长没挂组」的哨兵 team_id：恒等于任何真实团队，所以查出来必然是空集。
_NO_TEAM = -1


class Scope:
    """一次请求的可见范围。只暴露两个方法，所有权限判定都从它们走。"""

    def __init__(self, user: User, *, all_: bool, team_id: int | None = None):
        self.user = user
        self.all_ = all_
        self.team_id = team_id

    def on(self, column):
        """读：把过滤条件盖在某个「存 user_id 的列」上。

        用法：`q.filter(scope.on(AnnotationRecord.user_id))`

        ★ 用子查询而不是把组员 id 拉到 Python 里再 `in_([...])`：
          组员进出无需重算，IN 列表也不会随着团队变大涨到几千项。
        """
        if self.all_:
            return true()
        if self.team_id is not None:
            return column.in_(self._team_member_ids())
        return column == self.user.id

    def _team_member_ids(self) -> Select:
        return select(User.id).where(User.team_id == self.team_id)

    def covers(self, db: Session, owner_id: int) -> bool:
        """写：这条记录的所有者在不在范围内。

        ★ 刻意用查询而不是 Python 里比较 `owner.team_id == user.team_id`：
          后者会引入**第二处**「同组」判定，将来要改成一人管多组时，
          得改两个地方，漏一个就是「能看不能改」。复用 `on()` 的谓词，
          物理上保证读写一致。代价是一次主键上的 SELECT，可忽略。
        """
        if self.all_:
            return True
        return (
            db.query(User.id).filter(User.id == owner_id, self.on(User.id)).first()
            is not None
        )


def resolve_scope(db: Session, user: User) -> Scope:
    """当前用户的可见范围。"""
    if user.role in MANAGER_ROLES:
        return Scope(user, all_=True)
    if user.role == LEADER_ROLE:
        if user.team_id is None:
            # ★ 组长没挂组：空集，**绝不退化成「全部」**。
            #   这里写成 all_=True 的话，一个配置疏漏就等于「组长看到全公司」。
            return Scope(user, all_=False, team_id=_NO_TEAM)
        return Scope(user, all_=False, team_id=user.team_id)
    # employee，以及任何未知 role 值——一律降级为最窄，不降级为最宽
    return Scope(user, all_=False)


def assert_can_touch(db: Session, user: User, owner_id: int, *, detail: str = "记录不存在") -> bool:
    """能否改/删归属 `owner_id` 的记录。返回 True 表示「是别人的记录」（需要留痕）。

    ★ 越权一律 **404 而不是 403** —— 403 等于承认「这条存在」，是个存在性预言机。
      这是本平台的铁律（v1 起就写在 README 里）。

    ★ 调用方必须让「不存在」和「越权」走**同一句 detail 文案**，
      所以这里默认值就是列表接口用的那句「记录不存在」。
    """
    if owner_id == user.id:
        return False
    if not resolve_scope(db, user).covers(db, owner_id):
        raise HTTPException(status_code=404, detail=detail)
    return True


def visible_qc_filter(db: Session, user: User):
    """质检记录的可见 / 可改谓词。

    ★ 取**并集**：「我检的」∪「被检人在我范围内的」。

      只按被检人（`target_user_id`）判的话有个致命失败：质检员给**别组**的人做了
      一条质检，保存成功、列表刷新——**这条自己刚提交的记录不在列表里**，
      他既看不到也改不了。这不是泄密，是系统否认了他对自己提交数据的所有权，
      用户只会认为「系统丢数据了」。而跨组质检一定会有（否则「被质检人员」
      下拉为什么给他全量选项）。

    ★ 读和写共用这一个谓词。单条接口写成
      `db.query(QcRecord).filter(QcRecord.id == rid, visible_qc_filter(db, user)).first()`，
      一条查询同时完成「存在性」与「权限」，`None` 就 404 ——
      **物理上不给「取到了但忘了判权限」留空间**。
    """
    from ..models.qc_record import QcRecord  # 局部导入避免模型层与 core 层循环

    scope = resolve_scope(db, user)
    return or_(QcRecord.inspector_id == user.id, scope.on(QcRecord.target_user_id))
