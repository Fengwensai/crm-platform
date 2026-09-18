from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    # 工号：登录名
    username: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    status: str

    model_config = {"from_attributes": True}
