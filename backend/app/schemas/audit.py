from datetime import datetime

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    actor_id: int | None = None
    actor_name: str = ""
    action: str = ""
    target_type: str = ""
    target_id: str | None = None
    summary: str = ""
    detail: dict = {}
    ip: str = ""
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
