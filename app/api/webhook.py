from __future__ import annotations

import hashlib
import hmac
import uuid

import structlog
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict

from app.config import get_settings

router = APIRouter()
log = structlog.get_logger()


class PachcaWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    content: str
    chat_id: int
    user_id: int | None = None
    id: int | None = None


class WebhookResponse(BaseModel):
    status: str = "ok"


_ERROR_REPLY = (
    "Не удалось получить данные. Проверьте соединение с Tracker или повторите позже."
)


def _verify_signature(body: bytes, secret: str, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


@router.post("/webhook/pachca", response_model=WebhookResponse)
async def pachca_webhook(
    request: Request,
    payload: PachcaWebhookPayload,
    x_pachca_signature: str | None = Header(default=None, alias="X-Pachca-Signature"),
) -> WebhookResponse:
    settings = get_settings()
    body = await request.body()
    if not _verify_signature(body, settings.webhook_api_key, x_pachca_signature):
        log.warning("webhook.auth_failed", signature=x_pachca_signature)

    req_id = str(uuid.uuid4())[:8]
    bound_log = log.bind(req_id=req_id, chat_id=payload.chat_id, cmd=payload.content[:60])
    bound_log.info("webhook.received")

    command_router = request.app.state.command_router
    pachca = request.app.state.pachca

    try:
        reply = await command_router.handle(payload.chat_id, payload.content)
    except Exception:
        bound_log.exception("command.failed")
        reply = _ERROR_REPLY

    try:
        await pachca.send_message(payload.chat_id, reply)
        bound_log.info("webhook.done", reply_len=len(reply))
    except Exception:
        bound_log.exception("pachca.send_failed")

    return WebhookResponse()
