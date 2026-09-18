from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.deps import get_current_user
from ..core.netutil import client_ip
from ..core.ratelimit import allow as rate_allow
from ..core.security import create_access_token, hash_password, verify_password
from ..db import get_db
from ..models.team import Team
from ..models.user import User
from ..schemas.auth import LoginIn, MeOut, RegisterIn, TokenOut

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    """员工自助注册（公开接口，无需登录）。

    注册后 status=pending，**登不上**，要等管理员核对工号姓名后审批通过。
    因为是公开接口，这里做了同 IP 限频防刷；被刷进来的最多是一堆 pending 账号，
    看不到任何数据、也无法登录。
    """
    ip = client_ip(request)
    if not rate_allow(
        "register", ip, settings.REGISTER_RATE_LIMIT, settings.REGISTER_RATE_WINDOW_SECONDS
    ):
        raise HTTPException(status_code=429, detail="注册过于频繁，请稍后再试")

    username = body.username.strip()
    name = body.name.strip()
    if not username or not name:
        raise HTTPException(status_code=422, detail="工号与姓名不能为空")

    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(
            status_code=409, detail="该工号已注册，如非本人操作请联系管理员"
        )

    db.add(
        User(
            username=username,
            name=name,
            password_hash=hash_password(body.password),
            role="employee",
            status="pending",
        )
    )
    db.commit()
    return {"ok": True, "message": "注册成功，请等待管理员审批通过后登录"}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not rate_allow(
        "login", ip, settings.LOGIN_RATE_LIMIT, settings.LOGIN_RATE_WINDOW_SECONDS
    ):
        raise HTTPException(status_code=429, detail="尝试过于频繁，请稍后再试")

    user = db.query(User).filter(User.username == body.username.strip()).first()
    # 统一提示「工号或密码错误」，不区分「账号不存在」与「密码错」，
    # 避免被用来枚举有效工号。
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="工号或密码错误")

    if user.status == "pending":
        raise HTTPException(status_code=403, detail="账号待管理员审批，暂时无法登录")
    if user.status == "rejected":
        raise HTTPException(status_code=403, detail="注册申请已被驳回，请联系管理员")
    if user.status == "disabled":
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")

    token = create_access_token({"user_id": user.id, "role": user.role})
    return TokenOut(access_token=token)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # `team_name` 不是模型字段，from_attributes 取不到，得单独查一次。
    # 这里刻意不做成 relationship：`/auth/me` 每次进后台都会调一次，
    # 为一个名字多带一次 lazy load 没必要，而且会让「序列化 User」随时可能触发
    # 隐藏的数据库往返（在别的地方就变成 N+1）。
    out = MeOut.model_validate(user)
    if user.team_id is not None:
        out.team_name = (
            db.query(Team.name).filter(Team.id == user.team_id).scalar() or ""
        )
    return out
