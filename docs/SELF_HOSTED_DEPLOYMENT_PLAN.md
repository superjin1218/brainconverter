# Supabase + Cloudflare Tunnel 자체 서버 운영 계획

작성일: 2026-10-04

이 문서는 현재 상태와 앞으로 실행할 작업을 정리한 계획이다. 체크되지 않은 항목은 실제 설정·검증이 완료된 것이 아니다. MyGPT에 이 문서를 전달해 절차를 검토받아도 된다. 실제 키·비밀번호·터널 토큰은 문서에 입력하지 않는다.

## 1. 운영 목표

- 최종 주소: **https://brainconverter.qlabcommunity.org**
- `qlabcommunity.org`은 Cloudflare에서 구매한 도메인이다.
- 루트 도메인은 커뮤니티 메인 사이트용으로 남기고, `brainconverter` 서브도메인만 이 앱에 연결한다.
- 웹서버: 이 Linux 컴퓨터의 FastAPI 앱.
- 외부 연결: Cloudflare Tunnel.
- 인증·승인·사용량·결과 저장: Supabase.
- 실제 전략 해석: 서버의 OpenAI API 키.
- 운영자가 등록하고 승인한 회원만 변환을 사용한다.
- 일반 회원은 관리자 기능과 서버 키를 사용할 수 없다.
- 로그인 페이지는 공개하고, 변환 API에서 인증과 승인을 검사한다.

```text
사용자 브라우저
  → HTTPS brainconverter.qlabcommunity.org
  → Cloudflare
  → 이 컴퓨터의 cloudflared
  → FastAPI / 127.0.0.1:8080
  → Supabase 및 OpenAI
```

Cloudflare와 Supabase 사이에 별도의 직접 연동을 만들 필요는 없다. 앱이 Supabase에 요청하고, Tunnel이 외부 사용자 요청을 앱에 전달한다.

## 2. 현재 상태

### 완료한 작업

- [x] GitHub 인증 후 저장소를 현재 폴더에 복제.
- [x] `.venv` 생성 및 `requirements.txt` 의존성 설치.
- [x] 로그인 없는 로컬 모의 서버를 시작하고 홈페이지 HTTP 200 확인.
- [x] `/api/health`의 `status=ok`, `provider=mock` 확인.
- [x] Git에서 제외되는 `.env.local` 템플릿 생성, 권한 `600` 설정.

저장소: https://github.com/blockcoder-sj/natural-language-brain-alpha-Converter

프로젝트 폴더: `/home/jinwoo/Desktop/brainconvertoe`

복제 당시 main 커밋: `4e24e1c`

Python: 3.12 계열. `python3 -m venv`는 ensurepip 부재로 실패하여 설치되어 있던 `uv`를 사용했다.

```bash
uv venv --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

FastAPI 진입점: `backend.app.main:app`

기존 모의 서버는 백그라운드로 시작했다. 이후 살아 있는지는 다시 확인해야 한다. 이 서버는 `AUTH_MODE=none`으로 시작했으며, 새 `.env.local` 템플릿을 읽고 실행한 서버가 아니다.

### 남은 작업

- [ ] 기존 Supabase 프로젝트 사용 여부 확정.
- [ ] 실제 Supabase URL·키 입력 및 연결 확인.
- [ ] DB 스키마·함수·권한·예산 정책 확인.
- [ ] 운영자·회원 상태 확인 및 로컬 로그인 검증.
- [ ] 공개 회원가입 차단.
- [ ] OpenAI 키 연결 및 운영 모드 전환.
- [ ] Cloudflare Tunnel 생성·서비스 설치·서브도메인 라우팅.
- [ ] 앱 자동 실행 서비스 등록.
- [ ] 외부 HTTPS 접속·권한·재부팅 검증.

## 3. 코드에서 확인한 운영 제약

`backend/app/membership.py`:

- Supabase `/auth/v1/user`로 로그인 신원을 확인한다.
- 이메일 확인 상태를 검사한다.
- `brain_access` RPC로 회원의 `status`, `role`을 확인한다.
- 변환에는 `approved` 상태가 필요하다.
- 회원 관리에는 `approved` 상태와 `admin` 역할이 필요하다.
- 세션은 HttpOnly 쿠키로 저장하고 production에서 Secure를 적용한다.
- 로그인 등 변경 요청은 `Origin`과 `APP_PUBLIC_URL`을 비교하며 `x-requested-with: brain-site`도 검사한다.

`APP_PUBLIC_URL`은 접속 주소와 정확히 일치해야 한다. 최종 값은 `https://brainconverter.qlabcommunity.org`이며, 현재 코드 기준으로 끝의 슬래시는 넣지 않는다.

`backend/app/config.py`는 production에서 `AUTH_MODE=none`을 허용하지 않는다. `backend/app/provider.py`는 production에서 mock 공급자로 변환하는 것을 차단한다. 개발용 로컬 키 설정 라우터는 development에서만 등록된다.

동시 실행 제한 일부는 프로세스 내부 Semaphore로 관리한다. 초기 운영은 Uvicorn worker 하나로 시작한다.

현재 화면과 API에 직접 회원가입 기능이 남아 있다. 지정 회원 전용 운영에서는 Supabase 신규 가입 차단과 함께 앱의 가입 UI·API를 비활성화하는 변경을 검토한다. 버튼을 숨기는 것만으로 Supabase 가입이 차단되지는 않는다.

## 4. Supabase부터 연결

### 4.1. 프로젝트 선택

기존 운영 사이트: https://natural-language-brain-alpha-harness.vercel.app

저장소 문서에 기재된 프로젝트: https://supabase.com/dashboard/project/sogpsiheygdwmhdlizvy

먼저 기존 프로젝트에 접근할 수 있는지, 기존 회원을 그대로 사용할지 확인한다. 기존 프로젝트를 사용하면 사용자·승인·사용량·예산·결과 저장 DB를 공유한다. 기존 Vercel이 계속 운영되면 두 사이트가 같은 데이터와 예산을 사용한다.

기존 사이트 종료는 별도 결정한다. Supabase Auth 설정 변경은 기존 사이트에도 영향을 줄 수 있다. 저장소 문서의 이전 설정 완료 기록만으로 현재 DB 상태를 정상이라고 단정하지 않는다.

### 4.2. 연결값 입력

Supabase 대시보드에서 다음 값을 확인하여 로컬 `.env.local`에 직접 입력한다.

| 환경변수 | 입력값 |
| --- | --- |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Publishable key |
| `SUPABASE_SECRET_KEY` | 서버 전용 Secret key |

키는 채팅·문서·Git·브라우저 코드·로그에 넣지 않는다. `.env.local`은 Git에서 제외하고 권한 `600`을 유지한다.

### 4.3. DB 읽기 전용 검증

관련 파일:

- `supabase/verify_membership.sql`
- `supabase/bootstrap_operator.sql`

마이그레이션:

- `supabase/migrations/202609270001_membership.sql`
- `supabase/migrations/202609270002_concurrency_queue.sql`
- `supabase/migrations/202609270003_ai_budget.sql`
- `supabase/migrations/202609270004_member_pages.sql`
- `supabase/migrations/202609280004_openai_budget.sql`
- `supabase/migrations/202609280005_gpt_usage_reset.sql`

SQL Editor에서 읽기 전용 검증을 먼저 수행한다. 회원·작업·승인 이력 테이블, 필요한 `brain_*` 함수, RLS·테이블 접근 권한·함수 실행 권한·예산 정책을 확인한다. `verify_membership.sql`만으로 모든 예산 정책 확인이 완료되는 것은 아니므로 예산 테이블과 관련 함수도 확인한다.

기존 DB에는 적용 여부와 현재 정의를 확인하고 필요한 변경만 적용한다. 새 프로젝트는 파일 의존성을 확인하여 필요한 마이그레이션을 순서대로 적용한다.

**`202609280005_gpt_usage_reset.sql`은 최초 적용 시 누적 예산을 초기화한다.** 서버 이전을 위해 이 파일을 무조건 실행하지 않는다. 기존 비용·사용량은 보존한다. 이 파일의 함수 변경이 현재 앱에 필요한지 확인하고, 필요하면 초기화 동작과 분리한 마이그레이션으로 검토한다.

### 4.4. 지정 회원 전용 정책

1. 이메일·비밀번호 로그인은 유지한다.
2. Supabase Auth의 신규 공개 가입 허용을 끈다.
3. 운영자가 Users 화면에서 회원을 생성한다.
4. 운영자가 확인한 계정은 이메일 확인 상태도 설정한다.
5. `private.brain_members`에 회원 레코드가 생성됐는지 확인한다.
6. 운영자 계정이 `approved/admin`인지 확인한다.
7. 이용할 회원은 사이트의 회원 승인 관리에서 승인한다.
8. 미승인 회원은 `pending`, 이용 중지 회원은 `suspended`로 둔다.

현재 `bootstrap_operator.sql`의 운영자 이메일은 `seungzookim@gmail.com`이다. 실제 사용할 운영자 이메일을 먼저 확인한다. 다른 사람의 이메일을 추측하여 관리자 권한을 부여하지 않는다.

### 4.5. 로컬 로그인 검증

Supabase 연결과 로그인만 먼저 확인하고 유료 생성은 수행하지 않는다.

```dotenv
APP_ENV=development
AUTH_MODE=supabase
HARNESS_PROVIDER=mock
APP_PUBLIC_URL=http://127.0.0.1:8080
```

접속 주소: `http://127.0.0.1:8080`

기존 로그인 없는 모의 서버를 해당 프로세스만 종료하고 `.env.local`을 읽는 서버로 교체한다. 다른 Python 서버를 일괄 종료하지 않는다.

확인 항목: 로그인 성공, 본인 회원 상태, 운영자 관리 권한, 미승인 회원 차단. 모의 변환도 DB 사용량 예약을 만들 수 있으므로 연결 확인을 위해 변환을 실행할 필요는 없다.

### 4.6. Supabase URL Configuration

새 사이트가 주 운영 주소가 되면 Site URL을 다음으로 설정한다.

```text
https://brainconverter.qlabcommunity.org
```

Redirect URLs에는 실제 필요한 주소를 등록한다.

```text
https://brainconverter.qlabcommunity.org/
http://127.0.0.1:8080/
```

기존 Vercel을 유지하면 필요한 기존 Redirect URL도 유지한다. 인증메일 등의 링크가 어느 주소로 이동하는지 확인한다.

## 5. 앱 운영 모드 전환

최종 `.env.local` 예시. 아래 `실제값`은 로컬 파일에서만 입력한다.

```dotenv
APP_ENV=production
AUTH_MODE=supabase
HARNESS_PROVIDER=openai
APP_PUBLIC_URL=https://brainconverter.qlabcommunity.org
SUPABASE_URL=실제값
SUPABASE_PUBLISHABLE_KEY=실제값
SUPABASE_SECRET_KEY=실제값
OPENAI_API_KEY=실제값
OPENAI_MODEL=gpt-5.4-mini
MAX_CONCURRENT_JOBS=20
MODEL_TIMEOUT_SECONDS=35
```

모델과 제한은 현재 앱 설정을 따른다. 다른 모델로 임의 변경하지 않는다.

8080 포트의 기존 서버와 충돌하지 않도록 확인한 후 운영 서버를 실행한다.

```bash
cd /home/jinwoo/Desktop/brainconvertoe
.venv/bin/uvicorn backend.app.main:app \
  --host 127.0.0.1 \
  --port 8080 \
  --workers 1 \
  --env-file .env.local
```

운영 모드는 Secure 쿠키와 공개 Origin을 사용하므로 최종 로그인 검증은 HTTPS 외부 주소에서 수행한다. localhost HTTP에서 운영 로그인이 안 된다는 이유로 인증을 끄지 않는다. `/api/health` 정상 응답은 Supabase 로그인과 실제 AI 생성 성공을 보장하지 않는다.

## 6. Cloudflare Tunnel 연결

### 6.1. 터널 생성·커넥터 설치

1. Cloudflare의 `qlabcommunity.org` 영역이 활성 상태인지 확인한다.
2. Networking → Tunnels 또는 Zero Trust의 Tunnel 메뉴를 연다.
3. Cloudflared 방식으로 `brainconverter-server` 터널을 만든다.
4. 실제 Linux 배포판과 CPU 아키텍처에 맞는 설치 안내를 선택한다.
5. 대시보드에서 표시하는 설치 명령을 이 컴퓨터에서 실행한다.
6. 대시보드에서 표시하는 터널 토큰으로 서비스 설치 명령을 실행한다.

```bash
sudo cloudflared service install <터널토큰>
```

실제 토큰은 문서·채팅에 공유하지 않는다. 기존 `cloudflared` 서비스가 있으면 확인하고 덮어쓰지 않는다. 대시보드에서 커넥터 연결 상태를 확인한다.

이 계획은 `cloudflared`를 호스트 Linux에서 실행하는 전제다. Docker로 실행하면 `localhost`의 대상이 달라지므로 임의로 변경하지 않는다.

### 6.2. 공개 경로·DNS

Published application routes 또는 Public Hostname에서 다음을 등록한다.

| 항목 | 값 |
| --- | --- |
| Subdomain | `brainconverter` |
| Domain | `qlabcommunity.org` |
| Path | 비움 |
| Service Type | `HTTP` |
| Service URL | `localhost:8080` |

대시보드가 터널용 DNS 레코드를 생성하는지 확인한다. 동일한 이름의 기존 DNS가 있으면 충돌을 확인한다. 집 공인 IP를 가리키는 A 레코드나 공유기 포트포워딩을 만들 필요는 없다. 루트 도메인의 DNS는 이번 작업에서 변경하지 않는다.

Cloudflare Access 로그인은 우선 추가하지 않는다. 회원 인증과 승인은 Supabase 및 앱에서 처리한다.

해당 호스트의 `/api/*` 캐시는 우회한다. 로그인·회원 상태·변환 결과에 전체 캐시 규칙을 적용하지 않는다.

## 7. 자동 실행과 운영

FastAPI를 `brainconverter.service`라는 systemd 서비스로 등록한다.

필수 설정:

- 일반 사용자 `jinwoo`로 실행.
- `WorkingDirectory=/home/jinwoo/Desktop/brainconvertoe`.
- `.venv/bin/uvicorn`의 절대 경로 사용.
- `.env.local`의 환경변수 읽기.
- `127.0.0.1:8080` 바인딩, worker 하나.
- 부팅 시 자동 실행, 실패 시 재시작.
- `journalctl`로 로그 확인 가능.

서비스의 시작·중지·재시작·상태 확인 명령:

```bash
sudo systemctl enable --now brainconverter
sudo systemctl status brainconverter
sudo systemctl restart brainconverter
sudo systemctl stop brainconverter
sudo journalctl -u brainconverter -n 100 --no-pager
```

위 명령은 서비스 파일을 실제 작성·등록한 뒤 사용한다. 현재 서비스 등록 완료를 의미하지 않는다.

`cloudflared` 서비스도 자동 실행과 로그를 확인한다. sudo 비밀번호가 필요한 작업은 사용자가 자신의 터미널에서 수행한다.

컴퓨터 자동 절전을 해제한다. 컴퓨터 또는 인터넷이 꺼지면 웹사이트가 중단된다. Supabase 클라우드 데이터가 유지되는 것과 웹사이트 가용성은 별개다.

## 8. 최종 검증

- [ ] 로컬 홈페이지·`/api/health` 응답 정상.
- [ ] FastAPI systemd 서비스 정상.
- [ ] cloudflared 서비스·터널 커넥터 정상.
- [ ] 외부 HTTPS 홈페이지 정상.
- [ ] 로그인 쿠키의 Secure·HttpOnly 확인.
- [ ] 비로그인 사용자의 변환 차단.
- [ ] 미승인 회원의 변환 차단.
- [ ] 승인 회원의 변환 허용.
- [ ] 일반 회원의 관리자 API 접근 차단.
- [ ] suspended 회원의 새 변환 차단.
- [ ] 공개 회원가입 차단.
- [ ] 개발용 로컬 키 설정 라우트 비활성화.
- [ ] 서버 키가 HTML·JS·응답·Git에 노출되지 않음.
- [ ] DB의 필요한 함수·권한·예산 정책 정상.
- [ ] 휴대폰 모바일 데이터에서 외부 접속 정상.
- [ ] 사용자가 정한 시간에 재부팅 후 앱·터널 자동 복구 확인.

유료 AI 생성은 인증·권한 검증을 마치고 사용자가 실제 생성 테스트를 하기로 했을 때 1건만 수행한다. 정상적으로 결과가 저장되고 사용량·예산이 반영되는지 확인한다. 로그인 없는 개발 모드로 우회하여 운영 검증을 대신하지 않는다.

## 9. MyGPT에 요청할 검토

이 계획에서 잘못된 부분과 빠진 부분을 먼저 수정한 뒤, Supabase부터 순서대로 안내해 달라. 각 단계마다 다음을 구분해 달라.

1. 사용자가 대시보드에서 할 일.
2. 로컬 명령 또는 수정할 파일과 정확한 값.
3. 성공 여부를 확인하는 방법.
4. 실패 시 확인할 항목.

현재 Supabase·Cloudflare 계정에 접근한 것처럼 답하지 말고 실제 확인이 필요한 사항을 표시해 달라. 키·비밀번호·터널 토큰을 채팅에 요구하지 말라. 저장소에 접근할 수 없으면 필요한 파일 내용만 요청해 달라.

## 10. 공식 참고 문서

- Cloudflare Tunnel 설정: https://developers.cloudflare.com/tunnel/get-started/
- Cloudflare Tunnel 라우팅: https://developers.cloudflare.com/tunnel/concepts/routing/
- Supabase API 키: https://supabase.com/docs/guides/getting-started/api-keys
- Supabase Auth 설정: https://supabase.com/docs/guides/auth/general-configuration
- Supabase Redirect URL: https://supabase.com/docs/guides/auth/redirect-urls
