from __future__ import annotations

import httpx

_MAX_MSG_LEN = 4_000


class PachcaClient:
    """Minimal Pachca API client for sending chat messages.

    API base: https://api.pachca.com/api/shared/v1
    Auth: Authorization: Bearer <token>

    Messages longer than _MAX_MSG_LEN are split on blank lines so each
    chunk stays under the limit.
    """

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(15.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def send_message(self, chat_id: int, content: str) -> None:
        for chunk in _split(content):
            await self._post(chat_id, chunk)

    async def ping(self) -> bool:
        """Return True if Pachca API is reachable and token is valid."""
        try:
            r = await self._http.get("/users/me")
            return r.status_code < 500
        except Exception:
            return False

    async def _post(self, chat_id: int, content: str) -> None:
        response = await self._http.post(
            "/messages",
            json={
                "message": {
                    "entity_type": "discussion",
                    "entity_id": chat_id,
                    "content": content,
                }
            },
        )
        response.raise_for_status()


def _split(text: str, limit: int = _MAX_MSG_LEN) -> list[str]:
    """Split text into chunks ≤ limit chars, breaking on blank lines."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in text.split("\n\n"):
        block = para + "\n\n"
        if current_len + len(block) > limit and current_parts:
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = []
            current_len = 0
        current_parts.append(para)
        current_len += len(block)

    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())

    return chunks or [text]
