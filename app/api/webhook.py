from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()


class PachcaWebhookPayload(BaseModel):
    message: str
    chat_id: int
    user_id: int | None = None
    message_id: int | None = None


class WebhookResponse(BaseModel):
    status: str = "ok"


@router.post("/webhook/pachca", response_model=WebhookResponse)
async def pachca_webhook(
    request: Request,
    payload: PachcaWebhookPayload,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> WebhookResponse:
    settings = get_settings()
    if x_api_key != settings.webhook_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")

    command_router = request.app.state.command_router
    pachca = request.app.state.pachca

    reply = await command_router.handle(payload.chat_id, payload.message)
    await pachca.send_message(payload.chat_id, reply)

    return WebhookResponse()
