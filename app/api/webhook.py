from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.config import get_settings

router = APIRouter()
log = structlog.get_logger()


class PachcaWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str
    chat_id: int
    user_id: int | None = None
    message_id: int | None = None


class WebhookResponse(BaseModel):
    status: str = "ok"


_ERROR_REPLY = (
    "Не удалось получить данные. Проверьте соединение с Tracker или повторите позже."
)


@router.post("/webhook/pachca", response_model=WebhookResponse)
async def pachca_webhook(
    request: Request,
    payload: PachcaWebhookPayload,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> WebhookResponse:
    settings = get_settings()
    if x_api_key != settings.webhook_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")

    req_id = str(uuid.uuid4())[:8]
    bound_log = log.bind(req_id=req_id, chat_id=payload.chat_id, cmd=payload.message[:60])
    bound_log.info("webhook.received")

    command_router = request.app.state.command_router
    pachca = request.app.state.pachca

    try:
        reply = await command_router.handle(payload.chat_id, payload.message)
    except Exception:
        bound_log.exception("command.failed")
        reply = _ERROR_REPLY

    try:
        await pachca.send_message(payload.chat_id, reply)
        bound_log.info("webhook.done", reply_len=len(reply))
    except Exception:
        bound_log.exception("pachca.send_failed")

    return WebhookResponse()
