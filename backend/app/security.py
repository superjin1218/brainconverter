from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections.abc import Mapping

from .config import AppConfig


class GatewayVerifier:
    def __init__(self, config: AppConfig, clock=time.time) -> None:
        self.config = config
        self.clock = clock

    def protects(self, path: str) -> bool:
        return (
            self.config.is_production
            and self.config.auth_mode == "gateway"
            and path.rstrip("/") == "/api/convert"
        )

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        timestamp = headers.get("x-gateway-timestamp", "")
        signature = headers.get("x-gateway-signature", "")
        secret = self.config.gateway_shared_secret
        if not secret or not timestamp or not signature:
            return False
        try:
            if abs(self.clock() - int(timestamp)) > 90:
                return False
        except ValueError:
            return False
        email = headers.get("x-user-email", "")
        request_id = headers.get("x-request-id", "")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+", email) or not re.fullmatch(
            r"[a-zA-Z0-9-]{16,64}", request_id
        ):
            return False
        payload = f"{timestamp}\nPOST\n/api/convert\n{email}\n{request_id}\n".encode() + body
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def email_is_allowed(self, email: str) -> bool:
        return bool(email) and (
            not self.config.allowed_emails or email.lower() in self.config.allowed_emails
        )


class BodyLimitMiddleware:
    """Bound the body before FastAPI or authentication parses it, including chunked uploads."""

    def __init__(self, app, max_bytes=16384):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                from starlette.responses import JSONResponse

                response = JSONResponse(
                    {"detail": "요청 크기는 16KB 이하여야 합니다."},
                    status_code=413,
                    headers={"Cache-Control": "no-store"},
                )
                return await response(scope, receive, send)
            if not message.get("more_body"):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
