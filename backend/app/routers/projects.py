from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.audit import log_action
from ..core.deps import get_current_user, is_manager, require_manager
from ..core.guards import count_project_records, format_counts
from ..core.netutil import client_ip
from ..db import get_db
from ..models.project import Project
from ..models.user import User
from ..schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["项目"])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """项目列表。员工填报时要用（只看 active）；管理者管项目时看全部。"""
    q = db.query(Project)
    # 归档项目只有管理者能看见（员工填报选项里不该出现）
    if not (include_archived and is_manager(user)):
        q = q.filter(Project.status == "active")
    return q.order_by(Project.id.asc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    code = body.code.strip()
    if db.query(Project).filter(Project.code == code).first():
        raise HTTPException(status_code=409, detail="该项目编号已存在")
    # `unit` 不再是入参（v2 起停用，见 schemas/project.py）。列还在模型上，
    # 所以这里不传就会落到列默认值——**不要**在这里再补一个 "框"：
    # 那是给一个恒不被读取的列写一个看似正确的值，只会让下一个人以为它在生效。
    p = Project(code=code, name=body.name.strip(), status="active")
    db.add(p)
    db.flush()
    log_action(
        db,
        actor=manager,
        action="新建项目",
        target_type="project",
        target_id=p.id,
        summary=f"项目「{p.name}」({p.code})",
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(p)
    return p


@router.patch("/{pid}", response_model=ProjectOut)
def update_project(
    pid: int,
    body: ProjectUpdate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 快照里**不含 `unit`**：它已经不是可改字段，放进去只会让每条审计都带一个
    # 永远不会变的键。
    before = {"name": p.name, "status": p.status}
    if body.name is not None:
        p.name = body.name.strip()
    if body.status is not None:
        if body.status not in ("active", "archived"):
            raise HTTPException(status_code=422, detail="状态只能是 active 或 archived")
        p.status = body.status

    after = {"name": p.name, "status": p.status}
    if before != after:
        log_action(
            db,
            actor=manager,
            action="修改项目",
            target_type="project",
            target_id=p.id,
            summary=f"项目「{p.name}」({p.code})：{before} → {after}",
            detail={"before": before, "after": after},
            ip=client_ip(request),
        )
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{pid}")
def delete_project(
    pid: int,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """删除项目。已有历史数据的项目**不允许删**（会变成孤儿数据），
    应改为「归档」——归档后不再出现在填报选项里，历史数据完好。

    ★ 守卫查的是**标注 + 质检 + v1 填报**三处，见 core/guards.py。
    """
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    counts = count_project_records(db, pid)
    if counts:
        raise HTTPException(
            status_code=422,
            detail=f"该项目已有{format_counts(counts)}，不能删除；请改为「归档」",
        )
    log_action(
        db,
        actor=manager,
        action="删除项目",
        target_type="project",
        target_id=p.id,
        summary=f"项目「{p.name}」({p.code})",
        ip=client_ip(request),
    )
    db.delete(p)
    db.commit()
    return {"ok": True}
