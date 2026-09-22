#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

"""Passkey（WebAuthn）登录与凭据管理。

- 登录（无需会话）：`POST /api/login/passkey/options` 获取挑战 → 浏览器
  `navigator.credentials.get()` → `POST /api/login/passkey/verify` 验证断言并直接
  创建已激活会话，绕过原来的「聊天内输入激活码」流程。
- 注册（需已登录会话）：`POST /api/passkeys/register/options` → 浏览器
  `navigator.credentials.create()` → `POST /api/passkeys/register/verify` 保存公钥。

安全约定：
- 挑战使用密码学安全随机数，入库存储（含用途 / 归属用户 / 期望 origin 与 rp_id /
  过期时间），验证成功后立即删除（一次性），并定期清理过期挑战。
- 期望 origin 严格取配置 `PASSKEY_ORIGIN`；未配置时回退到创建挑战请求的 `Origin`
  头（仅建议本地开发，生产必须显式配置），该值随挑战一并落库，验证时按行内值校验。
"""

import json
import secrets
from datetime import timedelta
from typing import Any, Optional, cast
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app, logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larkuser.user.base import MoonlarkUser
from nonebot_plugin_orm import get_session
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json_dict
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..config import config
from ..models import PasskeyChallenge, PasskeyCredential
from ..rate_limit import rate_limit
from ..session import (
    create_session,
    get_user_data,
    get_user_id,
    utcnow,
)

app: FastAPI = cast("FastAPI", get_app())


# ── 请求模型 ──


class PasskeyLoginOptionsRequest(BaseModel):
    user_id: Optional[str] = None  # 传入时限定只允许该用户的凭据；留空走可发现凭据（resident key）


class PasskeyBrowserCredential(BaseModel):
    """浏览器 PublicKeyCredential 的 JSON 形态（camelCase），验证时直接交给 py_webauthn 解析。"""

    id: str
    raw_id: str = Field(alias="rawId")
    response: dict[str, Any]
    type: str = "public-key"
    authenticator_attachment: Optional[str] = Field(default=None, alias="authenticatorAttachment")

    def to_browser_json(self, exclude: set[str] | None = None) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude=exclude or set())


class PasskeyLoginVerifyRequest(PasskeyBrowserCredential):
    retention_days: Optional[int] = None  # 「记住我」天数，缺省用服务端默认值


class PasskeyRegisterOptionsRequest(BaseModel):
    device_name: str = "Passkey 设备"


class PasskeyRegisterVerifyRequest(PasskeyBrowserCredential):
    device_name: str = "Passkey 设备"


# ── 工具函数 ──


def _effective_origin(request: Request) -> str:
    """WebAuthn 期望 origin：优先配置项；未配置时回退请求头（本地开发）。"""
    if config.passkey_origin:
        return config.passkey_origin
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme and parsed.netloc:
            logger.warning("PASSKEY_ORIGIN 未配置，使用请求头 Origin 作为 WebAuthn origin（仅建议开发环境）")
            return f"{parsed.scheme}://{parsed.netloc}"
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Passkey 尚未配置：请设置 PASSKEY_ORIGIN 环境变量",
    )


def _effective_rp_id(request: Request, origin: str) -> str:
    if config.passkey_rp_id:
        return config.passkey_rp_id
    hostname = urlparse(origin).hostname
    if hostname:
        return hostname
    return (request.headers.get("Host") or "localhost").split(":")[0]


def _options_to_dict(options: Any) -> dict[str, Any]:
    """把 py_webauthn 生成的选项序列化成浏览器可直接使用的 JSON（库官方实现）。"""
    return options_to_json_dict(options)


async def _store_challenge(purpose: str, user_id: Optional[str], origin: str, rp_id: str) -> bytes:
    challenge = secrets.token_bytes(32)
    async with get_session() as session:
        session.add(
            PasskeyChallenge(
                challenge=challenge.hex(),
                purpose=purpose,
                user_id=user_id,
                origin=origin,
                rp_id=rp_id,
                expires_at=utcnow() + timedelta(seconds=config.passkey_challenge_ttl),
            ),
        )
        await session.commit()
    return challenge


async def _consume_challenge(
    challenge: bytes,
    purpose: str,
    user_id: Optional[str],
) -> tuple[str, str, Optional[str]]:
    """按挑战查找并删除（一次性）对应记录，返回 (期望 origin, rp_id, 归属用户)。

    无效 / 过期 / 归属不符时返回 400。
    """
    key = challenge.hex()
    async with get_session() as session:
        data = await session.get(PasskeyChallenge, key)
        if data is None or data.purpose != purpose or data.expires_at <= utcnow():
            if data is not None:
                await session.delete(data)
                await session.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 挑战无效或已过期")
        if user_id is not None and data.user_id != user_id:
            await session.delete(data)
            await session.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 挑战与当前用户不匹配")
        origin, rp_id, bound_user = data.origin, data.rp_id, data.user_id
        await session.delete(data)
        await session.commit()
        return origin, rp_id, bound_user


def _challenge_within_client_data(client_data_json_b64: str) -> bytes:
    """从浏览器回传的 clientDataJSON 中取出原始挑战（用于定位服务端存储的挑战）。"""
    try:
        client_data = json.loads(base64url_to_bytes(client_data_json_b64))
        return base64url_to_bytes(client_data["challenge"])
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clientDataJSON 解析失败",
        ) from e


def _credential_id_from_url(path_credential_id: str) -> bytes:
    try:
        return base64url_to_bytes(path_credential_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="凭据 ID 格式错误") from e


# ── 登录：Passkey 免密登录 ──


@app.post("/api/login/passkey/options")
async def login_passkey_options(
    request: Request,
    data: PasskeyLoginOptionsRequest,
    _: None = rate_limit(config.login_rate_limit_times, config.login_rate_limit_window_seconds),
) -> dict[str, Any]:
    """为一次 Passkey 登录颁发挑战。`user_id` 可选：传入则只允许该用户的凭据。"""
    origin = _effective_origin(request)
    rp_id = _effective_rp_id(request, origin)
    allow_credentials: list[PublicKeyCredentialDescriptor] = []
    if data.user_id:
        async with get_session() as session:
            result = await session.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == data.user_id))
            credentials = result.all()
        if not credentials:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该用户尚未注册 Passkey")
        allow_credentials = [
            PublicKeyCredentialDescriptor(type=PublicKeyCredentialType.PUBLIC_KEY, id=credential.credential_id)
            for credential in credentials
        ]
    challenge = await _store_challenge("login", data.user_id, origin, rp_id)
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        timeout=60_000,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return _options_to_dict(options)


@app.post("/api/login/passkey/verify")
async def login_passkey_verify(
    request: Request,
    data: PasskeyLoginVerifyRequest,
    _: None = rate_limit(config.login_rate_limit_times, config.login_rate_limit_window_seconds),
) -> dict[str, Any]:
    """验证 Passkey 断言；通过后直接创建已激活的 Web 会话。"""
    challenge = _challenge_within_client_data(data.response["clientDataJSON"])
    origin, rp_id, bound_user = await _consume_challenge(challenge, "login", None)
    credential_id = base64url_to_bytes(data.id)
    async with get_session() as session:
        credential = await session.scalar(
            select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id),
        )
        if credential is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到对应的 Passkey 凭据")
        if bound_user is not None and credential.user_id != bound_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 凭据与请求的用户不匹配")
        try:
            verification = verify_authentication_response(
                credential=data.to_browser_json(exclude={"retention_days"}),
                expected_challenge=challenge,
                expected_origin=origin,
                expected_rp_id=rp_id,
                credential_public_key=credential.public_key,
                credential_current_sign_count=credential.sign_count,
            )
        except InvalidAuthenticationResponse as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Passkey 登录验证失败: {e}") from e
        credential.sign_count = verification.new_sign_count
        credential.last_used_at = utcnow()
        user_id = credential.user_id
        await session.commit()
    session_id, _ = await create_session(
        user_id,
        request,
        data.retention_days or config.session_retention_days,
        activated=True,
    )
    return {
        "session_id": session_id,
        "user_id": user_id,
        "command_prefix": config.command_start[0],
    }


# ── 凭据管理：注册 / 列表 / 重命名 / 删除（需已登录会话） ──


@app.post("/api/passkeys/register/options")
async def passkey_register_options(
    request: Request,
    user_data: MoonlarkUser = get_user_data(),
) -> dict[str, Any]:
    """为当前登录用户颁发注册挑战（绑定其账号）。"""
    user_id = user_data.user_id
    origin = _effective_origin(request)
    rp_id = _effective_rp_id(request, origin)
    async with get_session() as session:
        result = await session.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == user_id))
        credentials = result.all()
        if len(credentials) >= config.passkey_max_credentials:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"每个账号最多可添加 {config.passkey_max_credentials} 个 Passkey",
            )
        exclude_credentials = [
            PublicKeyCredentialDescriptor(type=PublicKeyCredentialType.PUBLIC_KEY, id=credential.credential_id)
            for credential in credentials
        ]
    challenge = await _store_challenge("register", user_id, origin, rp_id)
    display_name = user_data.get_nickname() or user_id
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=config.passkey_rp_name,
        user_id=user_id.encode("utf-8"),
        user_name=user_id,
        user_display_name=display_name,
        challenge=challenge,
        timeout=60_000,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude_credentials,
    )
    return _options_to_dict(options)


@app.post("/api/passkeys/register/verify")
async def passkey_register_verify(
    data: PasskeyRegisterVerifyRequest,
    user_data: MoonlarkUser = get_user_data(),
) -> dict[str, Any]:
    """校验注册证明并保存公钥。"""
    user_id = user_data.user_id
    challenge = _challenge_within_client_data(data.response["clientDataJSON"])
    origin, rp_id, _ = await _consume_challenge(challenge, "register", user_id)
    try:
        verification = verify_registration_response(
            credential=data.to_browser_json(exclude={"device_name"}),
            expected_challenge=challenge,
            expected_origin=origin,
            expected_rp_id=rp_id,
        )
    except InvalidRegistrationResponse as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Passkey 注册验证失败: {e}") from e
    async with get_session() as session:
        duplicate = await session.scalar(
            select(PasskeyCredential).where(PasskeyCredential.credential_id == verification.credential_id),
        )
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该 Passkey 已注册，无需重复添加")
        session.add(
            PasskeyCredential(
                user_id=user_id,
                credential_id=verification.credential_id,
                public_key=verification.credential_public_key,
                sign_count=verification.sign_count,
                device_name=data.device_name,
            ),
        )
        await session.commit()
    return {"success": True, "message": "Passkey 已添加"}


@app.get("/api/passkeys")
async def passkey_list(user_id: str = get_user_id()) -> list[dict[str, Any]]:
    """列出当前账号的全部 Passkey。"""
    async with get_session() as session:
        result = await session.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == user_id))
        credentials = result.all()
        return [
            {
                "id": bytes_to_base64url(credential.credential_id),
                "device_name": credential.device_name,
                "created_at": credential.created_at.timestamp() if credential.created_at else None,
                "last_used_at": credential.last_used_at.timestamp() if credential.last_used_at else None,
            }
            for credential in credentials
        ]


@app.patch("/api/passkeys/{credential_id}")
async def passkey_rename(
    credential_id: str,
    data: PasskeyRegisterOptionsRequest,  # 仅使用 device_name 字段
    user_id: str = get_user_id(),
) -> dict[str, Any]:
    """重命名某个 Passkey 的显示名称。"""
    cid = _credential_id_from_url(credential_id)
    async with get_session() as session:
        credential = await session.scalar(
            select(PasskeyCredential).where(
                PasskeyCredential.credential_id == cid,
                PasskeyCredential.user_id == user_id,
            ),
        )
        if credential is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该 Passkey")
        credential.device_name = data.device_name
        await session.commit()
    return {"success": True, "message": "已重命名"}


@app.delete("/api/passkeys/{credential_id}")
async def passkey_delete(
    credential_id: str,
    user_id: str = get_user_id(),
) -> dict[str, Any]:
    """删除某个 Passkey。"""
    cid = _credential_id_from_url(credential_id)
    async with get_session() as session:
        result = await session.execute(
            delete(PasskeyCredential).where(
                PasskeyCredential.credential_id == cid,
                PasskeyCredential.user_id == user_id,
            ),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该 Passkey")
        await session.commit()
    return {"success": True, "message": "Passkey 已删除"}


# ── 维护 ──


@scheduler.scheduled_job("interval", minutes=10, id="remove_expired_passkey_challenges")
async def _remove_expired_challenges() -> None:
    session = get_session()
    result = await session.scalars(select(PasskeyChallenge).where(PasskeyChallenge.expires_at <= utcnow()))
    for item in result.all():
        await session.delete(item)
    await session.commit()
    await session.close()
