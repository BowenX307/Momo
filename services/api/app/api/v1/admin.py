"""Admin endpoints for live-editing the LLM personas + sampling params.

Auth: a single admin token (``settings.admin_token``) sent in the
``X-Admin-Token`` request header. If the token is unset on the server, every
endpoint returns 503 (feature disabled) so it can never be exposed by accident.
All mutations go through ``runtime_config`` (atomic write + timestamped backup).
"""

from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.llm import runtime_config
from app.llm.defaults import DEFAULT_PERSONAS, PERSONA_KEYS

router = APIRouter(prefix="/admin", tags=["admin"])

_MAX_PERSONA_CHARS = 8000


def _check_auth(token: str | None) -> None:
    expected = settings.admin_token or ""
    if not expected:
        raise HTTPException(status_code=503, detail="admin disabled (no token set)")
    if not hmac.compare_digest(token or "", expected):
        time.sleep(0.5)  # throttle brute force
        raise HTTPException(status_code=401, detail="unauthorized")


class Params(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: str = Field(min_length=1, max_length=100)
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(ge=0.0, le=1.0)
    frequency_penalty: float = Field(ge=-2.0, le=2.0)
    presence_penalty: float = Field(ge=-2.0, le=2.0)
    max_tokens: int = Field(ge=1, le=4096)


class ConfigUpdate(BaseModel):
    personas: dict[str, str]
    params: Params


@router.get("/verify")
async def verify(x_admin_token: str | None = Header(default=None)):
    _check_auth(x_admin_token)
    return {"ok": True}


@router.get("/llm-config")
async def get_llm_config(x_admin_token: str | None = Header(default=None)):
    _check_auth(x_admin_token)
    cfg = runtime_config.get_config(force=True)
    return {
        "personas": cfg["personas"],
        "params": cfg["params"],
        "defaults": runtime_config.get_defaults(),
        "persona_keys": list(DEFAULT_PERSONAS.keys()),
    }


@router.put("/llm-config")
async def put_llm_config(
    body: ConfigUpdate, x_admin_token: str | None = Header(default=None)
):
    _check_auth(x_admin_token)
    personas: dict[str, str] = {}
    for key, value in body.personas.items():
        if key not in PERSONA_KEYS:
            continue
        if not value or not value.strip():
            raise HTTPException(status_code=422, detail=f"persona '{key}' is empty")
        if len(value) > _MAX_PERSONA_CHARS:
            raise HTTPException(
                status_code=422,
                detail=f"persona '{key}' exceeds {_MAX_PERSONA_CHARS} chars",
            )
        personas[key] = value
    if not personas:
        raise HTTPException(status_code=422, detail="no valid personas provided")

    cfg = runtime_config.save_overrides(personas, body.params.model_dump())
    return {"ok": True, "personas": cfg["personas"], "params": cfg["params"]}


@router.post("/llm-config/reset")
async def reset_llm_config(x_admin_token: str | None = Header(default=None)):
    _check_auth(x_admin_token)
    cfg = runtime_config.reset_overrides()
    return {"ok": True, "personas": cfg["personas"], "params": cfg["params"]}
