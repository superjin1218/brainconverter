from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    environment: str
    gateway_shared_secret: str
    allowed_emails: frozenset[str]
    static_directory: Path

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_environment(cls) -> AppConfig:
        emails = frozenset(
            email.strip().lower()
            for email in os.getenv("ALLOWED_EMAILS", "").split(",")
            if email.strip()
        )
        return cls(
            environment=os.getenv("APP_ENV", "development").lower(),
            gateway_shared_secret=os.getenv("GATEWAY_SHARED_SECRET", ""),
            allowed_emails=emails,
            static_directory=Path(__file__).resolve().parent / "static",
        )

