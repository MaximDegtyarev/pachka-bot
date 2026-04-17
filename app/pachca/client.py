from __future__ import annotations

import httpx


class PachcaClient:
    """Minimal Pachca API client for sending chat messages.

    API base: https://api.pachca.com/api/shared/v1
    Auth: Authorization: Bearer <token>
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

    async def send_message(self, chat_id: int, content: str) -> dict:
        response = await self._http.post(
            "/messages",
            json={"message": {"entity_type": "discussion", "entity_id": chat_id, "content": content}},
        )
        response.raise_for_status()
        return response.json()
