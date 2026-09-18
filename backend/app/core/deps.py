from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.user import User
from .security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

MANAGER_ROLES = ("manager", "super_admin")


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
