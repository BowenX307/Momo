"""登录(手机号 + 验证码)相关 Pydantic schema。"""

import re

from pydantic import BaseModel, Field, field_validator

_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _validate_phone(v: str) -> str:
    if not _PHONE_RE.match(v):
        raise ValueError("invalid phone number")
    return v


class SendCodeRequest(BaseModel):
    """请求发送验证码。"""

    phone_number: str = Field(..., description="中国大陆手机号，11 位")

    _validate = field_validator("phone_number")(_validate_phone)


class SendCodeResponse(BaseModel):
    ok: bool = True


class VerifyCodeRequest(BaseModel):
    """校验验证码并登录。"""

    phone_number: str
    code: str = Field(..., min_length=4, max_length=8)
    external_user_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="当前浏览器的匿名标识；这个手机号没绑过人时会绑定到这个匿名用户上",
    )

    _validate = field_validator("phone_number")(_validate_phone)


class VerifyCodeResponse(BaseModel):
    """登录成功返回的 token。"""

    token: str
    external_user_id: str = Field(
        description="登录后应使用的匿名标识；如果手机号已绑定过老用户，"
        "这里会是老用户的 external_id（可能和请求里传入的不一样，前端要用这个覆盖本地存储）",
    )
    expires_in_seconds: int


class LogoutRequest(BaseModel):
    token: str


class MeResponse(BaseModel):
    external_user_id: str
    phone_number: str | None = None
