import json
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from scripts import deploy_openai as deployment

FAKE_KEY = "sk-deployment-placeholder-never-a-real-key"


def test_environment_keeps_key_literal_and_rejects_other_project(tmp_path, monkeypatch):
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setattr(deployment, "run", lambda *a, **k: "")
    path = tmp_path / ".env.local"
    path.write_text(
        f"OPENAI_API_KEY={FAKE_KEY}${{HOME}}\n"
        f"SUPABASE_URL=https://{deployment.SUPABASE_REF}.supabase.co\n"
        "SUPABASE_SECRET_KEY=fake-secret\nSUPABASE_PUBLISHABLE_KEY=fake-public\n"
    )
    assert deployment.environment()["OPENAI_API_KEY"].endswith("${HOME}")
    path.write_text(path.read_text().replace(deployment.SUPABASE_REF, "other-project"))
    with pytest.raises(RuntimeError, match="운영 Supabase"):
        deployment.environment()


def test_cli_failures_never_reflect_stdin_or_upstream_secret(monkeypatch):
    captured = []

    def fake_run(args, **kwargs):
        captured.append((args, kwargs))
        return subprocess.CompletedProcess(args, 1, stdout=FAKE_KEY, stderr=FAKE_KEY)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as failure:
        deployment.vercel("env", "add", "OPENAI_API_KEY", "production", value=FAKE_KEY)
    assert FAKE_KEY not in str(failure.value)
    assert FAKE_KEY not in " ".join(captured[0][0])
    assert captured[0][1]["input"] == FAKE_KEY
    assert captured[0][1]["capture_output"] is True


def test_migration_without_management_credential_stops_before_mutation(monkeypatch):
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("must not mutate"))
    with pytest.raises(RuntimeError, match="DB 업그레이드"):
        deployment.migrate({})


def test_check_only_mode_never_runs_cli_tests_migration_or_deploy(monkeypatch, capsys):
    class ReadOnlyProvider:
        def __init__(self, *, api_key):
            assert api_key == FAKE_KEY

        async def check_connection(self):
            return {"status": "ok", "inferencePerformed": False}

    monkeypatch.setattr(deployment, "environment", lambda: {"OPENAI_API_KEY": FAKE_KEY})
    monkeypatch.setattr(deployment, "OpenAIProvider", ReadOnlyProvider)
    monkeypatch.setattr(deployment, "budget_ready", lambda values: False)
    monkeypatch.setattr(deployment, "check_link", lambda: None)
    monkeypatch.setattr(deployment, "run", lambda *a, **k: pytest.fail("no CLI in check mode"))
    monkeypatch.setattr(deployment, "migrate", lambda *a: pytest.fail("no migration in check mode"))
    monkeypatch.setattr(deployment, "deploy", lambda *a: pytest.fail("no deployment in check mode"))
    monkeypatch.setattr(deployment.sys, "argv", ["deploy_openai.py", "--check"])
    deployment.main()
    output = capsys.readouterr().out
    assert "업그레이드 필요" in output
    assert FAKE_KEY not in output


def test_deployment_uploads_key_only_to_production_stdin_and_checks_revision(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    calls = []

    def cli(*args, value=None, **kwargs):
        calls.append((args, value))
        if args[0] == "link":
            folder = tmp_path / ".vercel"
            folder.mkdir()
            (folder / "project.json").write_text(json.dumps({"projectName": deployment.PROJECT}))
        return ""

    monkeypatch.setattr(deployment, "vercel", cli)
    monkeypatch.setattr(
        deployment, "diagnostic_runtime", lambda: {"providerSourceSha256": "expected-revision"},
    )
    monkeypatch.setattr(httpx, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"provider": "openai", "model": "gpt-5.4-mini", "providerRevision": "old"},
    ))
    with pytest.raises(RuntimeError, match="배포 후"):
        deployment.deploy({
            "OPENAI_API_KEY": FAKE_KEY,
            "SUPABASE_URL": f"https://{deployment.SUPABASE_REF}.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "fake-public", "SUPABASE_SECRET_KEY": "fake-secret",
        })
    uploads = [(args, value) for args, value in calls if "OPENAI_API_KEY" in args]
    assert len(uploads) == 1
    assert uploads[0][1] == FAKE_KEY
    assert "production" in uploads[0][0] and "--sensitive" in uploads[0][0]
    assert all(FAKE_KEY not in " ".join(args) for args, _ in calls)
