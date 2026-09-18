"""填报规则：哪些日期能填、能改。

两条轨（标注 / 质检）共用，所以单独成模块——写在 `annotations.py` 里再让
`qc.py` 复制一份的话，将来改窗口天数就会只改一边。
"""

from datetime import date, timedelta

from fastapi import HTTPException

from ..models.user import User
from .config import settings
from .deps import is_leader, is_manager
from .scope import resolve_scope
from .tz import today_cn


def assert_date_allowed(user: User, d: date) -> None:
    """填报/修改的日期闸门。

    ★ 「不能填未来」对**所有人**生效，包括超管。
      一条日期是明天的记录会让「今日工作量」永远对不上，而它没有任何正当用途。

    ★ 「只能改最近 N 天」对**管理者与组长豁免**。

      这个窗口的用途是防止**员工翻旧账改自己的历史**；而组长/管理者改他人数据
      本来就全程留痕（审计日志 before→after + 记录上的 `edited_by_manager` 标记）。
      若不对组长豁免，计划里「组长可改组员记录」这条规则在 7 天以前就名存实亡——
      界面上按钮点得动，一点就 422。

      相比 v1 有一处**刻意的放宽**：v1 在「新建」路径上对所有角色都拦窗口，
      于是管理者其实补录不了上周的账（v1 只在「修改」路径豁免）。这里两条
      路径一致豁免——「代填」和「代改」是同一件事，只差一个先有记录一个没有，
      没有理由是两种权限。
    """
    if d > today_cn():
        raise HTTPException(status_code=422, detail="不能填报未来日期")

    if is_manager(user) or is_leader(user):
        return

    if d < today_cn() - timedelta(days=settings.BACKFILL_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"只能填报或修改最近 {settings.BACKFILL_DAYS} 天内的数据",
        )


def resolve_owner(
    db, user: User, requested_id: int | None, *, detail: str = "指定的员工不存在"
) -> tuple[int, bool]:
    """这条记录归谁。返回 `(owner_id, 是否属于代填/需留痕)`。

    · 不传 / 传自己 → 归自己
    · 传范围内的人 → 归他，且标记需要留痕
    · **越权 → 404**（detail 与「账号不存在」同一句，让两者无法区分）

    ★ 这里相对 v1 是**行为变更**，而且必须变：v1 把员工传的 `user_id`
      一律**忽略**。加了组长之后，这条规则变成 bug——

        组长传一个**别组**组员的 `user_id`，被忽略后这条记录静默落到组长自己名下。
        组长本人也是标注员，他名下多一条毫不显眼。一条错数据就这么产生了，
        而且不报任何错，双方都不会发现。

      「忽略」是无声的，「404」是有声的。宁可报错也不能默默写错数据。

    ★ 归属判定必须**早于一切因数据内容而异的校验**（日期闸门、项目是否存在、
      条目号是否合法……）。否则「越权 + 日期非法 → 422」和「越权 + 日期合法 → 404」
      合起来就是个存在性预言机：拿不同的参数去试，能反推出这条记录存不存在。
    """
    if requested_id is None or requested_id == user.id:
        return user.id, False

    if not resolve_scope(db, user).covers(db, requested_id):
        raise HTTPException(status_code=404, detail=detail)
    return requested_id, True
