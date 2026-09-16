from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping

from .config import AppConfig


class GatewayVerifier:
    def __init__(self, config: AppConfig, clock=time.time) -> None:
        self.config = config
        self.clock = clock

    def protects(self, path: str) -> bool:
        return self.config.is_production and path == "/api/convert"

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        timestamp = headers.get("x-gateway-timestamp", "")
        signature = headers.get("x-gateway-signature", "")
        secret = self.config.gateway_shared_secret
        if not secret or not timestamp or not signature:
            return False
        try:
            if abs(self.clock() - int(timestamp)) > 300:
                return False
        except ValueError:
            return False
        payload = timestamp.encode() + b"." + body
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def email_is_allowed(self, email: str) -> bool:
        return not self.config.allowed_emails or email.lower() in self.config.allowed_emails

