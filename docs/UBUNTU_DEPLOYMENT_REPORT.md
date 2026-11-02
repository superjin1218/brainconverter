# Ubuntu 프로덕션 배포 진행 보고서

점검일: 2026-10-28. **Ubuntu 웹서비스 배포와 기존 Cloudflare Tunnel의 외부 HTTPS 연결을 완료했다.** `https://brainconverter.qlabcommunity.org`에서 실제 로그인·회원가입 페이지를 제공하며, 앱·터널은 모두 active/enabled다. 실제 이메일 발송·인증·로그인·관리자 승인과 전체 DB 카탈로그 감사, 호스트 재부팅 검증은 남아 있다. HTTP 검사 증거는 `UBUNTU_VERIFICATION.json`, 자동 복구·실행 보안 증거는 `UBUNTU_SERVICE_VERIFICATION.json`, 재배포 절차는 `UBUNTU_OPERATIONS.md`에 기록했다.

## 1. 실제 기술 스택과 발견한 차이

| 항목 | 실제 확인 |
| --- | --- |
| Python | 3.12.3, 기존 `.venv` 재사용 |
| Backend | FastAPI 0.142.2, Uvicorn 0.54.0, HTTPX 0.28.1, Pydantic 2.13.5 |
| ASGI | `backend.app.main:app` |
| Frontend | `backend/app/static`의 정적 HTML, ES modules, CSS; 별도 Node 번들 빌드 없음 |
| Supabase | HTTPX를 통한 Auth API·PostgREST RPC; 브라우저 SDK 없음 |
| 환경변수 | 앱은 프로세스 환경을 읽음. systemd EnvironmentFile 로딩을 별도 transient unit으로 확인 |
| 기존 환경 파일 | development / mock / localhost:8080 설정이었음. production / Supabase / canonical HTTPS / AI 중지로 변경 |
| AI 키 | 사용자 설명과 달리 `.env.local`에 비어 있지 않은 항목이 존재. 내용·유효성 미확인, 키 보존. 서비스에서 제외하도록 구성 |
| 기존 문서 | 8080번 포트·신규 가입 차단·이전 Vercel 사이트 기록이 있음. 이번 요청의 3000번 포트·공개 가입·메일 인증 정책 우선 |
| make | 설치되지 않음. 추가 시스템 패키지 설치 없이 Python·Node 명령으로 검증 |

기존 `.venv`의 검증한 런타임 23개 패키지 버전을 `deploy/requirements.lock`에 고정했다. 테스트 도구는 `requirements-dev.txt`로 설치했다. Python compileall, Ruff, systemd 유닛 검증, 설치 스크립트 구문 검사를 통과했다.

## 2. 수정·생성 파일

수정:

- `backend/app/config.py`: `CONVERSIONS_ENABLED` 설정과 잘못된 값 거부.
- `backend/app/conversion.py`: 인증·승인 확인 후, AI 초기화·작업/예산 예약 전에 중지.
- `backend/app/main.py`: 인증 콜백 페이지, 운영 Host 검증, 공개 HTTP→HTTPS 이동, 캐시·CSP·HSTS·권한 정책 헤더, AI 중지 상태 및 진단 차단.
- `backend/app/membership.py`: 가입 메일 콜백 경로, Supabase 토큰 검증용 confirmation API, 로그아웃 쿠키 속성.
- `backend/app/static/index.html`: 가입·이메일 인증·승인 순서 안내.
- `backend/app/static/js/membership.js`: URL 자격증명 처리와 인증 결과 안내.
- `backend/app/static/js/provider.js`: AI 준비 중 표시와 변환 요청 차단.
- `backend/tests/test_membership.py`, `backend/tests/frontend_state.test.mjs`: 콜백·보안·AI 중지 회귀 검증.
- `Makefile`, `.github/workflows/ci.yml`: 새 프런트엔드 테스트와 운영 검증 코드 lint 포함.
- `README.md`: Ubuntu 운영·검증 문서 연결.
- `.env.local`: 운영 플래그만 수정. 기존 키 보존, 600·Git 제외 유지.

생성:

- `backend/app/static/js/auth-callback.js`
- `backend/tests/auth_callback.test.mjs`
- `deploy/brainconverter.service`
- `deploy/install-systemd.sh`
- `deploy/requirements.lock`
- `scripts/check_production_config.py`
- `scripts/verify_production.py`
- `supabase/audit_production_readonly.sql`
- `docs/superpowers/plans/2026-10-28-ubuntu-production.md`
- `docs/UBUNTU_OPERATIONS.md`, `docs/UBUNTU_VERIFICATION.json`, `docs/UBUNTU_SERVICE_VERIFICATION.json`, 이 보고서

기존 미추적 파일 `docs/SELF_HOSTED_DEPLOYMENT_PLAN.md`는 보존했다. Git 커밋·푸시·Vercel 배포는 수행하지 않았다.

## 3. Ubuntu 서비스와 실행 상태

| 서비스 | 확인 상태 |
| --- | --- |
| `cloudflared.service` | active / running / enabled |
| `brainconverter.service` | active / running / enabled, `/etc/systemd/system/brainconverter.service` |
| `127.0.0.1:3000` | Uvicorn 정상 바인딩; 외부 인터페이스에 바인딩하지 않음 |
| 임시 검증 서버 | 127.0.0.1:13000에서 production 설정 검증. 최종 서비스가 아니며 점검 후 종료 |

설치한 시스템 유닛은 `jinwoo` 사용자, 127.0.0.1:3000, worker 1개, Restart=on-failure, RestartSec=5, multi-user.target 자동 시작을 사용한다. 환경 파일 600과 시작 전 검증을 적용하고 `OPENAI_API_KEY`를 프로세스에서 제외한다. 읽기 전용 파일시스템 등 서비스 격리 설정을 포함한다. 설치 유닛의 root 소유·644 권한·소스와의 일치, 실제 프로세스의 production/Supabase/AI 중지 설정·OpenAI 키 부재·NoNewPrivs=1·effective capabilities=0을 확인했다.

사용자가 승인한 설치 스크립트를 sudo로 실행했고, journal에서 실제 기동을 확인했다. 앱 프로세스만 의도적으로 SIGKILL한 자동 복구 시험에서 MainPID 47259→48502, NRestarts 0→1, 약 5.86초 뒤 health 정상 복구를 확인했다. 로그의 14:42:27 `status=9/KILL`은 이 시험으로 발생했으며 현재 서비스는 정상이다. 실제 호스트 재부팅은 수행하지 않았다.

최초 설치 중 sudo의 PATH에 `rg`가 없어 포트 검사 파이프라인이 실패했지만 설치가 계속되는 스크립트 문제를 확인했다. 당시 3000번 포트가 비어 있었고 현재 단일 앱 리스너만 존재한다. 스크립트를 `ss` 결과와 shell 내장 검사로 변경했고, `ss` 실행 실패도 설치를 중단하도록 수정했다. 이미 설치한 유닛을 다시 설치할 필요는 없다.

## 4. Cloudflare 외부 접속

`https://brainconverter.qlabcommunity.org/`는 실제 Brain Converter HTML을 HTTP 200으로 반환한다. 정적 JS·CSS·인증 콜백 페이지·보안 헤더를 확인했고, 외부/로컬 HTML·JS·CSS 해시와 API 상태가 일치한다. 외부 `CF-Ray` 존재, `CF-Cache-Status: DYNAMIC`, no-store를 확인했다. 초기 502는 웹서버 설치·기동 후 해소됐다.

Tunnel·DNS·Published Application을 생성하거나 변경하지 않았다. 공개 HTTP 주소가 처음에는 로그인 HTML을 제공하는 것을 발견해, 앱에서 공개 호스트의 HTTP 요청을 canonical HTTPS로 308 이동하도록 수정했다. loopback HTTP 상태 검사는 유지된다. 자동 재시작 후 외부 HTTP→HTTPS 이동을 실서버에서 확인했다. 실제 로그인 쿠키 발급은 아직 미검증이다.

## 5. Supabase 실서버 연결

실서버의 읽기 전용 검사 **18개 통과**:

- Auth Health HTTP 200.
- 회원가입 허용, 이메일 인증 필수, 이메일 공급자 활성, 익명 로그인 비활성.
- 서버 키로 앱이 사용하는 RPC 11개 등록 확인.
- 서비스 전용 읽기 RPC `brain_openai_budget_ready()`의 ready=true, allowanceKrw=34 확인. 비용을 예약하거나 초기화하지 않음.
- private 테이블 5개의 REST 스키마 접근 거부(PGRST106).
- 익명 사용자의 `brain_access`, 회원 조회, 사용량, 예산·readiness 조회 거부(401 / 42501).

이 검사는 전체 RLS·authenticated/service_role 권한 감사와 다르다. DB 연결 문자열·Management API 접근이 없어 실제 카탈로그 감사는 실행하지 않았다. 별도 READ ONLY SQL을 준비했다.

## 6. 회원가입·이메일 인증·로그인

| 항목 | 결과 |
| --- | --- |
| 가입 UI·이름 입력·가입 요청 구조 | 자동 테스트 및 외부 HTTPS Chromium 표시 확인 |
| Supabase 이메일 인증 기본 링크 호환 | 공식 implicit flow에 맞춰 콜백 구현; 모의 인증 응답으로 검증 |
| URL 토큰·오류 제거 | 단위 테스트 및 외부 HTTPS Chromium의 만료 링크로 확인 |
| 토큰 신뢰 검사 | Supabase `/auth/v1/user`에 확인. 실제 잘못된 JWT는 401 |
| 로그인/refresh HttpOnly·Secure·SameSite=Lax 쿠키 | 모의 Supabase 로그인 응답으로 검증; 실제 로그인 쿠키 발급 미검증 |
| 실제 회원 생성·Resend SMTP 발송·메일 수신 | 미실행: 계정 생성 허용/테스트 이메일 또는 사용자 직접 테스트 필요 |
| 실제 이메일 링크 클릭·비밀번호 로그인·로그아웃 | 미검증 |
| 신규 `pending/member` 등록 | 소스 기본값·트리거 확인. 현재 DB 카탈로그와 실제 신규 계정은 미검증 |

기본 ConfirmationURL은 Supabase가 이메일을 확인한 뒤 fragment로 토큰을 전달한다. 앱은 이를 지우고 토큰을 원격 검증하되 쿠키로 가져오지 않는다. 비밀번호 로그인을 따로 요구한다. 사용자 정의 token_hash 템플릿·PKCE/OAuth·비밀번호 복구를 지원 또는 검증했다고 주장하지 않는다. 공식 참고: [Supabase implicit flow](https://supabase.com/docs/guides/auth/sessions/implicit-flow), [이메일 템플릿](https://supabase.com/docs/guides/auth/auth-email-templates).

## 7. 관리자 승인

모의 Supabase 응답을 사용하는 테스트에서 pending/rejected/suspended 차단, approved 허용, 일반 회원의 관리자 API 거부, approved/admin 전용 회원 조회·승인 API를 검증했다. 외부 상태를 바꾸지 않는 실제 비로그인 관리자 API 요청도 401로 거부됐다.

실제 관리자 로그인, 회원 조회, 승인/거절/중지 변경은 수행하지 않았다. 테스트 계정을 만들거나 관리자 권한을 부여하지 않았으며 승인 데이터도 변경하지 않았다. 실제 승인 변경은 지정된 테스트 대상과 별도 허용이 필요하다.

## 8. 보안 점검

설치된 실제 서비스의 로컬 HTTP 검사 **40개**, 외부 HTTPS·리디렉션 검사 **41개 통과**. Supabase 18개와 합쳐 99개 검사이며, 서비스 재시작 후 다시 확인했다:

- 실제 HTML/JS/CSS, 콜백, HEAD, 인증 설정·AI 중지 상태.
- 비로그인 변환·회원·작업·사용량·관리자 API 접근 차단.
- 잘못된 JWT 거부, 다른 Origin·필수 사용자 정의 헤더 누락 차단.
- no-store, nosniff, DENY, no-referrer, CSP, HSTS, 공개 HTTP→HTTPS 308.
- `.env.local`, `.git/config`, 개발 문서·로컬 키 설정 API 비공개.
- 응답에 환경 파일의 알려진 키 값이 포함되지 않음.
- `.env.local` 600·Git 제외. 추적/새 코드·문서에서 알려진 자격증명 값 발견 없음.

Backend: **488 passed, 37 skipped**. SQL 테스트는 명시적으로 비활성화했다. Frontend: **46 passed**. 외부 서비스 호출은 자동 단위 테스트에서 모의 처리하며, 실서버 검증에서는 가입·로그인·작업/예산 예약·유료 AI를 실행하지 않는다. 테스트 도구의 deprecation 경고는 있으나 실패는 없다.

실제 Chromium으로 외부 HTTPS에서 로그인·가입 UI, 대시보드 비공개, URL 자격증명 제거, 만료 링크의 안전한 안내, JavaScript 예외 0개를 확인했다. 실제 계정 가입·로그인은 실행하지 않았다. 실제 로그인은 canonical 외부 HTTPS에서 검사해야 한다.

기존 마이그레이션, `202609280005_gpt_usage_reset.sql`, `bootstrap_operator.sql`, Vercel 배포 스크립트를 실행하지 않았다. 기존 회원·결과·예산·사용량을 삭제하거나 초기화하지 않았다. 유료 AI 호출도 수행하지 않았다.

## 9. 미검증 항목과 남은 문제

1. 승인된 테스트 계정 또는 사용자 직접 테스트로 Resend 발송/수신·이메일 인증·로그인·보안 쿠키·로그아웃 검증.
2. 기존 관리자 계정으로 승인 관리 검증. 승인 상태 변경은 대상별 허용 필요.
3. READ ONLY SQL로 현재 DB의 전체 RLS·스키마/테이블/모든 함수 overload 권한·가입 트리거 점검.
4. 별도 승인된 시간에 실제 호스트 재부팅 후 앱·터널 자동 복구 확인. 현재 자동 시작은 enabled이며 프로세스 오류 자동 복구는 실검증했다.
5. 다른 네트워크(휴대폰 모바일 데이터 등)에서 실제 사용자 접속 확인.

## 10. 재배포 명령

최초 설치는 사용자가 아래 명령으로 완료했다. 재실행하면 기존 유닛 보호를 위해 중단하므로 다시 설치하지 않는다. sudo 비밀번호를 채팅에 보내지 않는다.

```bash
cd /home/jinwoo/Desktop/brainconvertoe
sudo bash deploy/install-systemd.sh
```

설치 이후 코드 변경 재배포:

```bash
cd /home/jinwoo/Desktop/brainconvertoe
uv pip install --python .venv/bin/python -r deploy/requirements.lock
.venv/bin/pytest -q
node --test backend/tests/*.test.mjs
.venv/bin/ruff check backend scripts/check_production_config.py scripts/verify_production.py
.venv/bin/python -m scripts.check_production_config --env-file
sudo systemctl restart brainconverter.service
.venv/bin/python scripts/verify_production.py
```

## 11. 로그·장애 복구

```bash
systemctl is-active brainconverter.service cloudflared.service
systemctl is-enabled brainconverter.service cloudflared.service
journalctl -u brainconverter.service -n 100 --no-pager
journalctl -u brainconverter.service -f
```

원인 수정 후 복구:

```bash
sudo systemctl reset-failed brainconverter.service
sudo systemctl restart brainconverter.service
cd /home/jinwoo/Desktop/brainconvertoe
.venv/bin/python scripts/verify_production.py
```

cloudflared의 원문 서비스 상태/인수에는 토큰이 포함될 수 있어 공개 보고하지 않았다. 안전한 상태 확인과 터널 로그 취급·유닛 갱신·재부팅 검증 절차는 `UBUNTU_OPERATIONS.md`에 정리했다.
