from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    unit: str = Field(default="条", max_length=16)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    unit: str | None = Field(default=None, max_length=16)
    # active / archived
    status: str | None = None


class ProjectOut(BaseModel):
    id: int
    code: str
    name: str
    unit: str
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
