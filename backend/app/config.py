from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    environment: str
    static_directory: Path
    auth_mode: str = "supabase"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = field(default="", repr=False)
    public_url: str = ""
    conversions_enabled: bool = True

    def __post_init__(self) -> None:
        if self.auth_mode not in {"none", "supabase"}:
            raise ValueError("AUTH_MODE 설정을 확인하세요.")
        if self.is_production and self.auth_mode == "none":
            raise ValueError("운영 환경에서는 인증을 비활성화할 수 없습니다.")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_environment(cls) -> AppConfig:
        hosted = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") in {"production", "preview"}
        environment = os.getenv("APP_ENV", "production" if hosted else "development").lower()
        if hosted and environment != "production":
            raise ValueError("Vercel에서는 APP_ENV=production으로 설정하세요.")
        conversions_enabled = os.getenv("CONVERSIONS_ENABLED", "true").strip().lower()
        if conversions_enabled not in {"true", "false"}:
            raise ValueError("CONVERSIONS_ENABLED는 true 또는 false로 설정하세요.")
        return cls(
            environment=environment,
            static_directory=Path(__file__).resolve().parent / "static",
            auth_mode=os.getenv("AUTH_MODE", "supabase"),
            supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
            supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY", ""),
            supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY", ""),
            public_url=os.getenv("APP_PUBLIC_URL", "").rstrip("/"),
            conversions_enabled=conversions_enabled == "true",
        )
