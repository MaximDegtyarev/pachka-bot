from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()


class PachcaWebhookPayload(BaseModel):
    message: str
    chat_id: int | str
    user_id: int | str
    message_id: int | str | None = None


class WebhookResponse(BaseModel):
    response: str
    status: str = "success"


@router.post("/webhook/pachca", response_model=WebhookResponse)
async def pachca_webhook(
    payload: PachcaWebhookPayload,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> WebhookResponse:
    settings = get_settings()
    if x_api_key != settings.webhook_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")

    # TODO: route command to app.commands.router
    return WebhookResponse(response=f"received: {payload.message}")
