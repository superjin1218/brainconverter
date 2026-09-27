"""Transfer deployment configuration to Worker secrets without printing their values."""

import json
import os
import subprocess

names = ["BACKEND_URL", "ACCESS_TEAM_DOMAIN", "ACCESS_AUD", "ALLOWED_EMAILS", "ADMIN_EMAILS"]
secrets = {name: os.environ.get(name, "") for name in names}
secrets["GATEWAY_SHARED_SECRET"] = subprocess.check_output(
    [
        "gcloud",
        "secrets",
        "versions",
        "access",
        "latest",
        "--secret",
        "GATEWAY_SHARED_SECRET",
        "--project",
        os.environ["GCP_PROJECT_ID"],
    ],
    text=True,
).strip()
subprocess.run(
    ["npx", "wrangler", "secret", "bulk"],
    cwd="gateway",
    input=json.dumps(secrets),
    text=True,
    check=True,
)
