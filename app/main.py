from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router

app = FastAPI(title="pachka-bot", version="0.1.0")

app.include_router(health_router)
app.include_router(webhook_router)
