from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.user import User
from .scope import LEADER_ROLE, MANAGER_ROLES
from .security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

__all__ = [
    "LEADER_ROLE",
    "MANAGER_ROLES",
    "bearer_scheme",
    "get_current_user",
    "is_leader",
    "is_manager",
    "is_readonly",
    "reject_readonly_write",
    "require_manager",
    "require_super_admin",
]


def _decode(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        return decode_token(credentials.credentials)
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录"
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """统一鉴权入口。token 的 claim 是 user_id。

    这里同时守住 status：账号被停用或被驳回后，旧 token 即使没过期也立刻失效
    （否则管理员停用某人后，对方还能拿旧 token 继续操作）。
    """
    payload = _decode(credentials)
    user = db.get(User, payload.get("user_id"))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在")
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号未通过审批或已被停用"
        )
    return user


def require_manager(user: User = Depends(get_current_user)) -> User:
    """管理者（含超管）：可查看全员数据、审批账号、管理项目。"""
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理者权限")
    return user


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限"
        )
    return user


def is_manager(user: User) -> bool:
    return user.role in MANAGER_ROLES


def is_leader(user: User) -> bool:
    """是不是组长（能看本组）。注意组长**不是**管理者：打 `/api/users`、
    `/api/audit-logs` 这类管理者端点照样 403。"""
    return user.role == LEADER_ROLE and user.team_id is not None


def is_readonly(user: User) -> bool:
    """是不是只读演示账号。

    与 `role` / `scope` 正交：`scope.py` 决定「能看见谁的数据」，这个决定
    「看见之后能不能改」。所以它不该做进 scope，而应该在写操作之前先拦一道。
    """
    return bool(getattr(user, "is_readonly", False))


READ_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def reject_readonly_write(
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """只读演示账号发起写操作时一律 403。

    为什么不做进 `get_current_user`：它只看凭据、拿不到 HTTP 方法，而「只读」
    的本质恰恰是按方法区分的（读放行、写拒绝），所以只能在这里用
    `request.method` 判断。

    挂在哪些路由上见 `main.py` —— **`auth` 路由必须排除**：它的 `POST /login`
    与 `POST /register` 是公开接口，挂上去会让所有人（包括评委自己）登不进来。
    """
    if request.method in READ_SAFE_METHODS:
        return
    if is_readonly(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前为只读演示账号，不能修改数据",
        )
