# Brain Converter Ubuntu 운영

이 문서는 `/home/jinwoo/Desktop/brainconvertoe`를 위한 운영 절차다. 실제 검증 결과와 남은 작업은 `UBUNTU_DEPLOYMENT_REPORT.md`에서 구분한다. 이전 Vercel·8080번 포트·지정 회원 전용 계획보다 이번 Ubuntu 운영 요청이 우선한다.

## 구성

- Python 3.12 가상환경 `.venv`, FastAPI/Uvicorn 진입점 `backend.app.main:app`.
- 정적 HTML·ES modules·CSS는 `backend/app/static`에서 제공한다. Node 번들 빌드는 필요 없다.
- 운영 포트 `127.0.0.1:3000`, Uvicorn worker 1개.
- 외부 주소 `https://brainconverter.qlabcommunity.org`.
- 공개 호스트의 HTTP 요청은 앱에서 HTTPS로 308 이동한다. `127.0.0.1:3000`의 HTTP 상태 검사는 유지한다.
- 기존 `cloudflared.service`가 `http://localhost:3000`으로 연결한다. 터널·DNS는 변경하지 않는다.
- Supabase 프로젝트 `svdiaxzeqlouhhqwoayr`, 서버에서 HTTPX로 Auth API와 PostgREST RPC를 호출한다. Supabase 브라우저 SDK를 쓰지 않는다.
- `brainconverter.service`는 일반 사용자 `jinwoo`로 실행한다. 부팅 시 시작하고 오류 종료 시 5초 뒤 재시작한다. 60초에 5회 실패하면 재시작을 멈추므로 원인을 고친 뒤 `reset-failed`한다.

## 환경변수와 인증

OpenAI 키를 교체한 뒤 모델 정보 조회 HTTP 200과 `gpt-5.4-mini` 접근을 확인했다. 현재 실행 서비스는 아직 AI 중지 상태다. 활성화용 변경을 검토·승인한 뒤 아래 명령으로 적용한다. 기존 검토된 유닛만 갱신하며, 키·모델·34원/2만 원 정책을 읽기 전용으로 확인하고 서비스 재시작 실패 시 중지 상태로 복원한다. 실제 유료 변환은 테스트하지 않는다.

```bash
cd /home/jinwoo/Desktop/brainconvertoe
sudo bash deploy/enable-ai.sh
```

이 명령은 기존 유닛을 `.pre-ai`로 보존하고, 서비스의 OpenAI 키 제외 설정을 제거하며 `.env.local`의 `CONVERSIONS_ENABLED=true`를 적용한다. 키 자체와 기존 DB 데이터는 보존한다. 활성화 후에는 승인된 회원의 변환 요청에 OpenAI 요금이 발생한다. 이미 적용했다면 최초 활성화 스크립트를 재실행하지 말고 일반 재시작 절차를 사용한다.

`.env.local`은 소유자 `jinwoo`, 권한 `600`, Git 제외 상태를 유지한다. 파일이나 `/proc/.../environ`의 원문을 로그·채팅에 출력하지 않는다. 앱의 `AppConfig`는 환경변수만 읽으며 `.env.local`을 자동으로 읽지 않는다. systemd가 `EnvironmentFile`로 로드하고, 수동 검증 명령만 `python-dotenv`를 사용한다.

```dotenv
APP_ENV=production
AUTH_MODE=supabase
APP_PUBLIC_URL=https://brainconverter.qlabcommunity.org
HARNESS_PROVIDER=openai
CONVERSIONS_ENABLED=false
```

Supabase URL·Publishable Key·Secret Key는 기존 파일의 값을 유지한다. 최초 설치한 운영 유닛의 `UnsetEnvironment=OPENAI_API_KEY`가 AI 키를 프로세스에서 제거한다. 위 활성화 명령은 이 설정을 해제한다. `CONVERSIONS_ENABLED=false`는 승인 검사 후 공급자 초기화·작업 예약·비용 예약 전에 변환을 503으로 중지한다. 관리자 AI 연결 진단도 중지한다. 인증과 회원 관리에는 AI 키가 필요 없다.

`/api/health`의 `status=ok`는 웹서버가 응답한다는 뜻이다. Supabase 로그인 성공이나 AI 생성 성공을 뜻하지 않는다. `conversionsEnabled`는 `.env.local`의 설정과 일치해야 한다. 인증 정책 변경 작업은 기존 AI 활성화 상태를 유지하며 유료 생성은 호출하지 않는다.

인증 흐름은 **회원가입 → 비밀번호 로그인 → 승인 대기 → 관리자 승인 → 변환**이다. 이메일 인증·Resend·가입메일용 SMTP에 의존하지 않는다. HTML·JavaScript·FastAPI는 비밀번호 6~256자를 검사하며 문자 조합 제한을 두지 않는다. Supabase 비밀번호 인증과 HttpOnly 세션은 유지한다.

Supabase 대시보드에서 신규 가입 허용 ON, Confirm email OFF, Minimum password length 6, 문자 조합 요구 없음, Custom SMTP OFF를 설정한다. Confirm email이 남아 있으면 가입 API는 메일 발송 전에 503으로 중단한다. 기존 프로젝트 SQL Editor에서 `supabase/migrations/202610310001_password_only_membership.sql` 전체만 실행한다. 이 업그레이드는 기존 회원·예산·작업 결과를 보존하며 재실행해도 초기화하지 않는다. 과거 `gpt_usage_reset` 파일을 운영 DB에 재실행하지 않는다.

신규 회원 트리거는 사용자 메타데이터와 무관하게 `pending/member`를 기록한다. 관리자 API·회원관리 RPC는 `approved/admin`, 변환과 사용량·비용 예약은 `approved` 상태를 요구한다. 이메일 인증 시각은 권한 판단에 쓰지 않는다. 기존 `/auth/callback`은 오래된 메일 링크의 URL 인증 값을 지운 뒤 비밀번호 로그인을 안내하며 세션을 만들거나 인증 API를 호출하지 않는다. `/api/auth/confirmation`은 폐기했다.

**사칭 위험:** 누구나 타인의 이름·이메일을 입력할 수 있다. Confirm email OFF의 자동 인증 시각은 실제 소유 증명이 아니며 관리자 화면의 이메일 주소나 이름만으로 승인하면 사칭 계정에 이용 권한을 부여할 수 있다. 기존 연락처·대면 확인 등 별도 신뢰 경로로 가입자를 확인한 뒤 승인한다. 이미 등록된 이메일을 다른 사람이 선점한 경우에도 임의로 계정을 승인하거나 합치지 않는다. 기존 계정의 비밀번호·관리자 역할은 변경하지 않는다. 첫 관리자 지정이 필요하면 신뢰된 SQL Editor에서 별도 확인한 UUID를 `brain.bootstrap_operator_id`에 지정하고 `supabase/bootstrap_operator.sql`을 실행한다. 이 작업에서 첫 관리자 지정 스크립트는 실행하지 않는다.

가입·로그인에 메일 발송은 필요 없다. 비밀번호 재설정·이메일 변경 등 향후 메일 기능을 추가할 때는 별도 정책과 발송 구성을 검토한다.

정책 근거: [Supabase 인증 설정](https://supabase.com/docs/guides/auth/general-configuration), [이메일 미확인 가입의 위험](https://supabase.com/docs/guides/auth/testing-auth-flows).

로그인과 refresh 응답만 `brain_access`와 `brain_refresh`를 HttpOnly·Secure·SameSite=Lax 쿠키로 설정한다. 경로는 각각 `/api`, `/api/auth`이며 Domain을 지정하지 않는다. 운영 로그인은 외부 HTTPS에서 진행해야 한다. 변경 요청에는 정확한 Origin과 `X-Requested-With: brain-site`가 필요하다. 서버는 Supabase `/auth/v1/user`로 JWT를 검증하고 `brain_access()`의 승인·역할을 확인한다. 일반 회원의 메타데이터로 승인·관리자 권한을 부여하지 않는다.

## 최초 설치 — 승인 후 실행

현재 컴퓨터의 최초 설치는 완료했다. 아래는 새 설치용 절차이며, 기존 유닛이 있는 상태에서 재실행하지 않는다. 준비된 유닛과 스크립트를 먼저 검토한다. 설치 스크립트는 기존 `brainconverter.service`나 3000번 포트 점유가 있으면 중단하며 `rg`에 의존하지 않는다. Supabase 마이그레이션과 Cloudflare 설정은 변경하지 않는다.

```bash
cd /home/jinwoo/Desktop/brainconvertoe
uv pip install --python .venv/bin/python -r deploy/requirements.lock
.venv/bin/python -m scripts.check_production_config --env-file
systemd-analyze verify deploy/brainconverter.service
sudo bash deploy/install-systemd.sh
```

새 환경에서 `.venv`가 없다면 먼저 `uv venv --python 3.12 .venv`를 실행한다. 기존 가상환경을 지우거나 다시 만들 필요는 없다. 설치 스크립트는 `/etc/systemd/system/brainconverter.service`에 root 소유 644로 설치한 뒤 daemon-reload, enable, start를 실행한다. 비밀 값은 유닛 파일에 쓰지 않는다.

## 코드 수정 후 재배포

검토한 로컬 코드를 기준으로 진행한다. 자동 Git pull·Vercel 배포·SQL 실행은 포함하지 않는다.

```bash
cd /home/jinwoo/Desktop/brainconvertoe
uv pip install --python .venv/bin/python -r deploy/requirements.lock
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/pytest -q
node --test backend/tests/frontend_state.test.mjs backend/tests/auth_callback.test.mjs
.venv/bin/ruff check backend scripts/check_production_config.py scripts/verify_production.py
.venv/bin/python -m scripts.check_production_config --env-file
sudo systemctl restart brainconverter.service
.venv/bin/python scripts/verify_production.py
```

HTML·JS·CSS는 별도 번들 빌드가 없다. Python 문법 빌드는 `.venv/bin/python -m compileall -q backend/app`로 확인할 수 있다. 버전 고정 파일은 이번에 검증한 설치 버전을 보존한다. 의존성을 의도적으로 바꿀 때만 lock을 갱신하고 다시 테스트한다.

유닛 자체를 수정했다면 내용을 검토하고 별도 승인 후 반영한다. 최초 설치 스크립트는 기존 유닛을 덮어쓰지 않는다.

```bash
systemd-analyze verify deploy/brainconverter.service
sudo install -o root -g root -m 0644 deploy/brainconverter.service /etc/systemd/system/brainconverter.service
sudo systemctl daemon-reload
sudo systemctl restart brainconverter.service
```

## 상태·로그·복구

```bash
systemctl is-active brainconverter.service cloudflared.service
systemctl is-enabled brainconverter.service cloudflared.service
systemctl show brainconverter.service -p ActiveState -p SubState -p MainPID -p NRestarts
systemctl show cloudflared.service -p ActiveState -p SubState -p UnitFileState
journalctl -u brainconverter.service -n 100 --no-pager
journalctl -u brainconverter.service -f
curl -I http://127.0.0.1:3000/
curl -I https://brainconverter.qlabcommunity.org/
```

`cloudflared`의 유닛·프로세스 인수에는 터널 토큰이 들어갈 수 있으므로 원문 `systemctl status/cat`·프로세스 목록을 채팅에 붙이지 않는다. 터널 로그가 필요하면 로컬에서 `sudo journalctl -u cloudflared.service -n 100 --no-pager`를 검토하고 비밀 값을 가린다. 앱은 URL의 인증 코드가 로그에 남지 않도록 Uvicorn access log를 끈다. 시작·실패·예외 로그는 journal에 남는다.

앱 오류를 고친 뒤 복구한다.

```bash
cd /home/jinwoo/Desktop/brainconvertoe
.venv/bin/python -m scripts.check_production_config --env-file
sudo systemctl reset-failed brainconverter.service
sudo systemctl restart brainconverter.service
systemctl is-active brainconverter.service
.venv/bin/python scripts/verify_production.py
```

502이면 먼저 로컬 3000번 포트와 앱 로그를 확인한다. 로컬이 정상일 때 기존 Tunnel 연결·대상 포트·네트워크 상태를 조사한다. 이 절차가 터널·DNS 재생성이나 설정 변경을 승인하는 것은 아니다. Supabase 로그인 장애는 Auth Health·외부 DNS·비밀번호 인증 설정으로 구분해 확인한다. 가입메일 SMTP는 이 흐름에 필요하지 않다.

## 실제 가입·승인 검증

유료 OpenAI를 호출하지 않고 검증한다. 자동화 테스트는 모의 Supabase/모의 모델, SQL 테스트는 폐기 가능한 로컬 PostgreSQL을 사용한다. 실제 서비스에 회원가입 테스트를 할 때는 별도 테스트 주소를 쓰고 기존 계정이나 예산을 초기화하지 않는다.

1. HTML·JS·FastAPI에서 빈 값·5자 이하 비밀번호를 거부하고 숫자만 6자, 영문만 6자를 허용하는지 확인한다.
2. 이메일 인증 없이 가입한 계정으로 로그인하여 `pending/member`와 승인 대기 화면을 확인한다.
3. 미승인 회원·미승인 관리자 역할이 변환·관리자 API와 권한이 필요한 RPC에 접근하지 못하는지 확인한다.
4. 기존 `approved/admin`으로 로그인하고 사칭 위험 안내 및 이메일 인증 여부와 관계없이 승인 가능한지 확인한다. 운영 승인 대상은 별도 신원 확인을 거친다.
5. 승인 후 화면·사용량 접근이 허용되는지 확인한다. 실제 운영 `/api/convert` 호출은 OpenAI 비용이 발생하므로 수행하지 않는다. 생성 성공은 모의 모델로 검증한다.
6. 로그아웃 후 API가 다시 401이 되는지 확인한다.
7. `.venv/bin/python scripts/verify_production.py --output docs/PASSWORD_ONLY_VERIFICATION.json`으로 로컬·공개 페이지 동일성, 미인증 차단, Supabase autoconfirm과 새 정책 RPC를 확인한다. 최소 길이·문자 조합·Custom SMTP는 공개 settings API에 없으므로 대시보드에서 별도 확인한다.

Docker가 없는 컴퓨터는 PostgreSQL 실행 파일 경로를 `BRAIN_TEST_PG_BIN`으로 지정하여 `RUN_SQL_TESTS=1 .venv/bin/pytest -q backend/tests/test_membership_sql.py`를 실행할 수 있다. 네트워크를 열지 않는 임시 Unix socket과 임시 DB를 사용하고 종료 시 제거한다.

전체 DB 권한 감사는 `supabase/audit_production_readonly.sql`을 해당 프로젝트 SQL Editor에서 실행한다. 트랜잭션은 READ ONLY이며 마지막에 ROLLBACK한다. RLS·private 스키마/테이블 권한·모든 RPC overload·SECURITY DEFINER search_path·가입 트리거·회원 기본값을 확인한다. REST의 private 스키마 비공개 확인만으로 전체 RLS 감사 완료를 선언하지 않는다.

## 재부팅 검증

`is-enabled`는 자동 시작 설정의 증거이며 실제 재부팅 성공의 증거는 아니다. 다른 작업에 영향을 주므로 재부팅은 사용자가 정한 시간에 별도 승인 후 진행한다. 재부팅 후 아래를 확인한다.

```bash
systemctl is-active brainconverter.service cloudflared.service
systemctl is-enabled brainconverter.service cloudflared.service
journalctl -b -u brainconverter.service -n 50 --no-pager
cd /home/jinwoo/Desktop/brainconvertoe
.venv/bin/python scripts/verify_production.py
```

컴퓨터·인터넷·절전 상태가 외부 서비스 가용성에 영향을 준다. 호스트 절전 정책은 이번 작업에서 변경하지 않는다.
