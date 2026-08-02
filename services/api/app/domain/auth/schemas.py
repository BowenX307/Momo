"""登录相关 Pydantic schema（手机号 + 验证码 / 密码两条路径）。"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64


def _validate_phone(v: str) -> str:
    if not _PHONE_RE.match(v):
        raise ValueError("invalid phone number")
    return v


def _validate_password(v: str) -> str:
    """密码强度下限。故意只拦最差的几种，不强制大小写/特殊字符——那种规则劝退多于防护。"""
    if not (PASSWORD_MIN_LENGTH <= len(v) <= PASSWORD_MAX_LENGTH):
        raise ValueError(
            f"password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters"
        )
    if v.isdigit():
        raise ValueError("password must not be all digits")
    return v


class _RejectPhoneAsPassword(BaseModel):
    """把「密码就是自己手机号」这种挡掉。需要同时有 phone_number 和 new_password 字段。"""

    @model_validator(mode="after")
    def _password_differs_from_phone(self):  # type: ignore[no-untyped-def]
        phone = getattr(self, "phone_number", None)
        password = getattr(self, "new_password", None)
        if phone and password and phone == password:
            raise ValueError("password must not be the phone number")
        return self


class SendCodeRequest(BaseModel):
    """请求发送验证码。"""

    phone_number: str = Field(..., description="中国大陆手机号，11 位")
    purpose: Literal["login", "reset"] = Field(
        default="login",
        description="验证码用途。为登录发的码不能用于重置密码，反之亦然",
    )

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
    agreed_to_terms: bool = Field(
        ..., description="是否已勾选同意用户协议；false 时后端直接拒绝，不建用户不签 token"
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


class PasswordLoginRequest(BaseModel):
    """手机号 + 密码登录。"""

    phone_number: str
    password: str = Field(..., min_length=1, max_length=PASSWORD_MAX_LENGTH)
    external_user_id: str = Field(..., min_length=1, max_length=128)
    agreed_to_terms: bool

    _validate = field_validator("phone_number")(_validate_phone)
    # 登录时**不**跑强度校验：库里可能有历史上按旧规则设的密码，
    # 在这里拦会把人锁在门外。强度只在「设置/重置密码」时把关。


class SetPasswordRequest(BaseModel):
    """已登录状态下设置或修改密码（走 Authorization 头认身份）。"""

    current_password: str | None = Field(
        default=None, description="已经设过密码时必填；首次设置留空"
    )
    new_password: str = Field(...)

    _validate = field_validator("new_password")(_validate_password)


class ResetPasswordRequest(_RejectPhoneAsPassword):
    """忘记密码：验证码验明身份后重设，并直接登录。"""

    phone_number: str
    code: str = Field(..., min_length=4, max_length=8)
    new_password: str = Field(...)
    external_user_id: str = Field(..., min_length=1, max_length=128)
    agreed_to_terms: bool

    _validate_phone_field = field_validator("phone_number")(_validate_phone)
    _validate_password_field = field_validator("new_password")(_validate_password)


class LogoutRequest(BaseModel):
    token: str


class MeResponse(BaseModel):
    external_user_id: str
    phone_number: str | None = None
    has_password: bool = Field(
        default=False, description="前端据此决定显示「设置密码」还是「修改密码」"
    )
    consent_version: str | None = None
