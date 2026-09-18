"""团队（分组）。仅管理者可见可改。

组长**不在**这里管团队——组长没有「管理团队」的权限，只有「看本组数据」的权限。
把团队管理收在 `require_manager` 后面，是让「组长」这个角色保持单一含义：
一个数据可见范围，而不是一个小号管理员。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.audit import log_action
from ..core.deps import require_manager
from ..core.netutil import client_ip
from ..db import get_db
from ..models.team import Team
from ..models.user import User
from ..schemas.team import TeamCreate, TeamOut, TeamUpdate

router = APIRouter(prefix="/api/teams", tags=["团队"])

TEAM_STATUSES = ("active", "archived")


def _leader_map(db: Session) -> dict[int, tuple[int, str]]:
    """`team_id -> (leader_id, leader_name)`，从 `User.role` 现算。

    ★ 这是**派生**的展示数据，不是第二个真相源。见 models/team.py：
      团队表上故意没有 leader_id 字段，就是为了避免「用户管理页把人降级了，
      但 leader_id 还指着他」这种两边都不报错的不一致。
    """
    rows = (
        db.query(User.team_id, User.id, User.name)
        .filter(User.role == "leader", User.team_id.isnot(None))
        .all()
    )
    return {tid: (uid, name) for tid, uid, name in rows}


def _member_counts(db: Session) -> dict[int, int]:
    rows = (
        db.query(User.team_id, func.count(User.id))
        .filter(User.team_id.isnot(None))
        .group_by(User.team_id)
        .all()
    )
    return {tid: int(n) for tid, n in rows}


def _enrich(db: Session, teams: list[Team]) -> list[TeamOut]:
    leaders = _leader_map(db)
    counts = _member_counts(db)
    return [
        TeamOut(
            id=t.id,
            name=t.name,
            status=t.status,
            remark=t.remark,
            member_count=counts.get(t.id, 0),
            leader_id=leaders.get(t.id, (None, ""))[0],
            leader_name=leaders.get(t.id, (None, ""))[1],
            created_at=t.created_at,
        )
        for t in teams
    ]


@router.get("", response_model=list[TeamOut])
def list_teams(
    include_archived: bool = False,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    q = db.query(Team)
    if not include_archived:
        q = q.filter(Team.status == "active")
    return _enrich(db, q.order_by(Team.id.asc()).all())


@router.post("", response_model=TeamOut, status_code=201)
def create_team(
    body: TeamCreate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if db.query(Team.id).filter(Team.name == name).first() is not None:
        # 409 而不是 422：这是「与现有资源冲突」，不是「参数格式不对」。
        raise HTTPException(status_code=409, detail="已有同名团队")

    t = Team(name=name, remark=body.remark.strip())
    db.add(t)
    db.flush()
    log_action(
        db,
        actor=manager,
        action="新建团队",
        target_type="team",
        target_id=t.id,
        summary=f"团队「{t.name}」",
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(t)
    return _enrich(db, [t])[0]


@router.patch("/{tid}", response_model=TeamOut)
def update_team(
    tid: int,
    body: TeamUpdate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    t = db.get(Team, tid)
    if t is None:
        raise HTTPException(status_code=404, detail="团队不存在")

    changes: list[str] = []

    if body.name is not None:
        name = body.name.strip()
        if name != t.name:
            dup = db.query(Team.id).filter(Team.name == name, Team.id != t.id).first()
            if dup is not None:
                raise HTTPException(status_code=409, detail="已有同名团队")
            changes.append(f"名称「{t.name}」→「{name}」")
            t.name = name

    if body.status is not None and body.status != t.status:
        if body.status not in TEAM_STATUSES:
            raise HTTPException(status_code=422, detail="状态只能是 active 或 archived")
        changes.append(f"状态 {t.status} → {body.status}")
        t.status = body.status

    if body.remark is not None and body.remark.strip() != t.remark:
        changes.append("备注已更新")
        t.remark = body.remark.strip()

    if changes:
        log_action(
            db,
            actor=manager,
            action="修改团队",
            target_type="team",
            target_id=t.id,
            summary=f"团队「{t.name}」：" + "；".join(changes),
            ip=client_ip(request),
        )
    db.commit()
    db.refresh(t)
    return _enrich(db, [t])[0]


@router.delete("/{tid}")
def delete_team(
    tid: int,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """删团队。**有成员的组不许删**——与「有记录的账号/项目不许删」同一条原则。

    直接把组删掉的话，组员会变成 `team_id` 指向一个不存在的团队：
    他们的数据还在，但组长看不见了，「本组」这个概念当场失效，而且不报任何错。
    正确做法是先把成员移出去，或者改为「归档」。

    （注意这里不需要像删账号那样检查历史记录：记录挂在**人**身上，
    删组不会让任何记录失去归属，只是让一组人失去归属。）
    """
    t = db.get(Team, tid)
    if t is None:
        raise HTTPException(status_code=404, detail="团队不存在")

    n = db.query(func.count(User.id)).filter(User.team_id == tid).scalar() or 0
    if n:
        raise HTTPException(
            status_code=422,
            detail=f"该团队还有 {n} 名成员，不能删除；请先把成员移出，或改为「归档」",
        )

    log_action(
        db,
        actor=manager,
        action="删除团队",
        target_type="team",
        target_id=t.id,
        summary=f"团队「{t.name}」",
        ip=client_ip(request),
    )
    db.delete(t)
    db.commit()
    return {"ok": True}
