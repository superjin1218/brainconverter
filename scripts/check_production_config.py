"""Validate production configuration without printing credentials or making network calls."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from backend.app.config import AppConfig
from backend.app.provider_config import OpenAIConnection

ROOT = Path(__file__).resolve().parents[1]


def validate() -> None:
    env_file = ROOT / ".env.local"
    if env_file.is_symlink() or stat.S_IMODE(env_file.stat().st_mode) != 0o600:
        raise ValueError(".env.local must be a regular file with permissions 600")
    if env_file.stat().st_uid != os.getuid():
        raise ValueError(".env.local must be owned by the service user")
    config = AppConfig.from_environment()
    if not config.is_production or config.auth_mode != "supabase":
        raise ValueError("APP_ENV=production and AUTH_MODE=supabase are required")
    origins = [("APP_PUBLIC_URL", config.public_url), ("SUPABASE_URL", config.supabase_url)]
    for name, value in origins:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment
        ):
            raise ValueError(name + " must be an HTTPS origin without credentials or path")
    if not config.supabase_publishable_key or not config.supabase_secret_key:
        raise ValueError("Both Supabase keys must be configured in .env.local")
    if os.getenv("HARNESS_PROVIDER") != "openai":
        raise ValueError("Production requires the OpenAI provider")
    if config.conversions_enabled:
        OpenAIConnection.from_environment()
    if not (config.static_directory / "index.html").is_file():
        raise ValueError("The static application is missing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", action="store_true", help="Load .env.local before validation")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(ROOT / ".env.local", override=True)
    try:
        validate()
    except (ValueError, OSError, RuntimeError):
        # Do not print exception data: environment values can contain credentials.
        print("Production preflight failed. Check AI/auth settings and .env.local mode/owner.")
        return 1
    mode = "enabled" if AppConfig.from_environment().conversions_enabled else "paused"
    print(f"Production preflight OK: Supabase auth, HTTPS origin, AI {mode}, secrets protected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
