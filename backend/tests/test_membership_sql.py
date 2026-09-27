"""Run the migration on disposable PostgreSQL; never connects to Supabase."""

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SQL_TESTS") != "1", reason="explicit local Docker test"
)
ADMIN = "10000000-0000-0000-0000-000000000001"
MEMBER = "10000000-0000-0000-0000-000000000002"
OTHER = "10000000-0000-0000-0000-000000000003"
UNCONFIRMED = "10000000-0000-0000-0000-000000000004"
HASH = "a" * 64
ROOT = Path(__file__).resolve().parents[2]


class Database:
    def __init__(self, container):
        self.container = container

    def run(self, sql, *, role=None, user=None, fails=False):
        if role:
            sql = (
                f"begin; set local role {role}; "
                f"select set_config('request.jwt.claim.sub','{user or ''}',true); {sql} commit;"
            )
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                self.container,
                "psql",
                "-U",
                "postgres",
                "-XqAt",
                "--set",
                "ON_ERROR_STOP=1",
            ],
            input=sql,
            text=True,
            capture_output=True,
            timeout=15,
        )
        if fails:
            assert result.returncode != 0, result.stdout
            return result.stderr
        assert result.returncode == 0, result.stderr
        return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""

    def rpc(self, function, args="", **kwargs):
        return json.loads(self.run(f"select public.{function}({args});", **kwargs))

    def reserve(self, user=MEMBER, request=None, request_hash=HASH):
        return self.rpc(
            "brain_reserve",
            f"'{user}','{request or uuid4()}','{request_hash}'",
            role="service_role",
        )


@pytest.fixture(scope="module")
def db():
    name = f"brain-membership-test-{uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=disposable-test-only",
            "--tmpfs",
            "/var/lib/postgresql/data",
            "postgres:16-alpine",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    database = Database(name)
    try:
        deadline = time.monotonic() + 20
        while subprocess.run(
            ["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True, timeout=5
        ).returncode:
            if time.monotonic() > deadline:
                raise AssertionError("Disposable PostgreSQL failed to start")
            time.sleep(0.1)
        database.run("""
            create role anon; create role authenticated; create role service_role bypassrls;
            create schema auth;
            create table auth.users(id uuid primary key, email text,
              email_confirmed_at timestamptz, raw_user_meta_data jsonb default '{}');
            create function auth.uid() returns uuid language sql stable as $$
              select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid;
            $$;
        """)
        for path in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            database.run(path.read_text())
            database.run(path.read_text())  # Every upgrade is rerunnable.
        yield database
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True, timeout=15)


@pytest.fixture(autouse=True)
def members(db):
    db.run(f"""
      truncate auth.users cascade;
      insert into auth.users(id,email,email_confirmed_at,raw_user_meta_data) values
        ('{ADMIN}','seungzookim@gmail.com',now(),'{{"display_name":"운영자"}}'),
        ('{MEMBER}','member@example.test',now(),'{{"role":"admin","status":"approved"}}'),
        ('{OTHER}','other@example.test',now(),'{{}}'),
        ('{UNCONFIRMED}','unconfirmed@example.test',null,'{{}}');
      update private.brain_members set role='admin',status='approved' where user_id='{ADMIN}';
    """)


def approve(db, user=MEMBER):
    return db.rpc(
        "brain_set_member_status", f"'{user}','approved'", role="authenticated", user=ADMIN
    )


def test_signup_metadata_cannot_approve_or_grant_admin(db):
    assert db.rpc("brain_access", role="authenticated", user=MEMBER) == {
        "status": "pending",
        "role": "member",
        "displayName": "",
    }
    assert db.reserve() == {"state": "denied"}


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_private_tables_and_server_jobs_are_inaccessible(db, role):
    for sql in (
        "select * from private.brain_members;",
        f"update private.brain_members set status='approved' where user_id='{MEMBER}';",
        f"select public.brain_reserve('{MEMBER}','{uuid4()}','{HASH}');",
        f"select public.brain_job('{MEMBER}','{uuid4()}');",
        f"select public.brain_finish('{MEMBER}','{uuid4()}','{{}}',false);",
    ):
        assert "permission denied" in db.run(sql, role=role, user=MEMBER, fails=True)


def test_ordinary_member_cannot_list_or_approve_anyone(db):
    approve(db)
    for sql in (
        "select public.brain_members();",
        f"select public.brain_set_member_status('{MEMBER}','approved');",
    ):
        assert "insufficient_privilege" in db.run(
            sql, role="authenticated", user=MEMBER, fails=True
        )


def test_admin_requires_confirmed_email_and_cannot_change_admin_accounts(db):
    for user, expected in (
        (UNCONFIRMED, "email confirmation required"),
        (ADMIN, "admin accounts require dashboard management"),
    ):
        assert expected in db.run(
            f"select public.brain_set_member_status('{user}','approved');",
            role="authenticated",
            user=ADMIN,
            fails=True,
        )
    assert approve(db) == {"id": MEMBER, "status": "approved"}
    assert db.run("select count(*) from private.brain_approval_audit;") != "0"


def test_admin_bootstrap_requires_verified_operator(db):
    db.run(
        f"update private.brain_members set role='member',status='pending' where user_id='{ADMIN}';"
    )
    bootstrap = (ROOT / "supabase/bootstrap_operator.sql").read_text()
    db.run(bootstrap)
    assert db.rpc("brain_access", role="authenticated", user=ADMIN)["role"] == "admin"
    db.run(f"update auth.users set email_confirmed_at=null where id='{ADMIN}';")
    assert "confirmed operator account required" in db.run(bootstrap, fails=True)


def test_reserved_request_reuses_result_and_cannot_cross_accounts_or_inputs(db):
    approve(db)
    approve(db, OTHER)
    request = str(uuid4())
    assert db.reserve(request=request)["state"] == "reserved"
    assert db.reserve(request=request)["state"] == "running"
    assert db.reserve(user=OTHER, request=request)["state"] == "conflict"
    assert db.reserve(request=request, request_hash="b" * 64)["state"] == "conflict"
    assert db.rpc("brain_job", f"'{OTHER}','{request}'", role="service_role")["state"] == "missing"
    assert db.rpc("brain_finish", f"'{OTHER}','{request}','{{}}',false", role="service_role") == {
        "saved": False
    }
    db.rpc(
        "brain_finish",
        f"'{MEMBER}','{request}','{{\"code\":\"rank(returns)\"}}',false",
        role="service_role",
    )
    assert db.reserve(request=request) == {"state": "cached", "result": {"code": "rank(returns)"}}
    assert db.run("select count(*) from private.brain_jobs;") == "1"


def test_revocation_immediately_blocks_new_and_cached_conversions(db):
    approve(db)
    request = str(uuid4())
    db.reserve(request=request)
    db.rpc("brain_finish", f"'{MEMBER}','{request}','{{}}',false", role="service_role")
    db.rpc("brain_set_member_status", f"'{MEMBER}','suspended'", role="authenticated", user=ADMIN)
    assert db.reserve(request=request)["state"] == "denied"
    assert db.reserve()["state"] == "denied"
    db.run("select public.brain_usage();", role="authenticated", user=MEMBER, fails=True)


@pytest.mark.parametrize("kind", ["daily", "monthly", "global_monthly"])
def test_database_enforces_usage_limits(db, kind):
    approve(db)
    count = {"daily": 20, "monthly": 50, "global_monthly": 1000}[kind]
    owner = ADMIN if kind == "global_monthly" else MEMBER
    start = "date_trunc('month',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'"
    if kind == "daily":
        start = "date_trunc('day',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'"
    db.run(f"""insert into private.brain_jobs(request_id,user_id,request_hash,status,started_at)
      select gen_random_uuid(),'{owner}','{HASH}','error',{start}
      from generate_series(1,{count});""")
    assert db.reserve()["state"] == "limited"


def test_parallel_reservations_never_exceed_global_running_limit(db):
    users = [str(uuid4()) for _ in range(24)]
    requests = [str(uuid4()) for _ in users]
    for user in users:
        db.run(f"insert into auth.users(id,email_confirmed_at) values('{user}',now());")
        approve(db, user)
    with ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(lambda pair: db.reserve(*pair), zip(users, requests)))
    assert sum(result["state"] == "reserved" for result in results) == 20
    assert sum(result["state"] == "queued" for result in results) == 4
    assert db.run("select count(*) from private.brain_jobs where status='running';") == "20"

    queued = json.loads(
        db.run("""select jsonb_agg(jsonb_build_array(user_id,request_id)
      order by started_at,request_id) from private.brain_jobs where status='queued';""")
    )
    # One finished slot belongs to the queue head, even when a later member polls first.
    owner, running = next(
        (user, request)
        for user, request, result in zip(users, requests, results)
        if result["state"] == "reserved"
    )
    db.rpc("brain_finish", f"'{owner}','{running}','{{}}',false", role="service_role")
    assert db.reserve(*queued[-1])["state"] == "queued"
    assert db.reserve(*queued[0])["state"] == "reserved"
    assert db.reserve(*queued[0])["state"] == "running"
    assert db.run("select count(*) from private.brain_jobs;") == "24"
    assert db.run("select count(*) from private.brain_jobs where status='running';") == "20"


def test_per_member_minute_limit_is_still_two(db):
    approve(db)
    assert db.reserve()["state"] == "reserved"
    assert db.reserve()["state"] == "reserved"
    assert db.reserve()["state"] == "limited"


def test_queue_claim_has_one_winner_and_expired_queue_does_not_restart(db):
    approve(db)
    request = str(uuid4())
    db.run(f"""insert into private.brain_jobs
      (request_id,user_id,request_hash,status,last_seen_at)
      values('{request}','{MEMBER}','{HASH}','queued',now());""")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: db.reserve(request=request), range(6)))
    assert sum(result["state"] == "reserved" for result in results) == 1
    assert sum(result["state"] == "running" for result in results) == 5
    db.run(f"""update private.brain_jobs set status='queued',
      last_seen_at=now()-interval '121 seconds' where request_id='{request}';""")
    assert db.reserve(request=request)["state"] == "error"
    assert db.run("select count(*) from private.brain_jobs;") == "1"


def test_queued_request_wait_over_two_minutes_uses_new_running_lease(db):
    approve(db)
    request = str(uuid4())
    db.run(f"""insert into private.brain_jobs
      (request_id,user_id,request_hash,status,started_at,last_seen_at)
      values('{request}','{MEMBER}','{HASH}','queued',now()-interval '3 minutes',now());""")
    assert db.reserve(request=request)["state"] == "reserved"
    assert db.rpc("brain_job", f"'{MEMBER}','{request}'", role="service_role")["state"] == "running"


def test_queue_upgrade_preserves_existing_data_and_permissions(db):
    approve(db)
    request = str(uuid4())
    db.reserve(request=request)
    db.run((ROOT / "supabase/migrations/202609270002_concurrency_queue.sql").read_text())
    assert db.rpc("brain_access", role="authenticated", user=MEMBER)["status"] == "approved"
    assert db.reserve(request=request)["state"] == "running"
    assert "permission denied" in db.run(
        f"select public.brain_reserve('{MEMBER}','{request}','{HASH}');",
        role="authenticated",
        user=MEMBER,
        fails=True,
    )


def test_expired_and_failed_requests_do_not_automatically_call_again(db):
    approve(db)
    request = str(uuid4())
    db.reserve(request=request)
    db.rpc("brain_finish", f"'{MEMBER}','{request}',null,true", role="service_role")
    assert db.reserve(request=request)["state"] == "error"
    db.run(
        f"update private.brain_jobs set status='done',result='{{}}',"
        f"finished_at=now()-interval '25 hours' where request_id='{request}';"
    )
    assert db.reserve(request=request)["state"] == "error"
