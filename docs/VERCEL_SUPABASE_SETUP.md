# Vercel + Supabase 회원 사이트 설정

2026-09-28 기준. **Supabase DB·운영자 로그인과 로컬 Meta Contributor 실제 변환 3건을 확인했습니다. 승인받은 진단 버전 `896e2be`가 Vercel Production에 Ready 상태로 배포됐으며, 배포 서버의 Meta 모델 목록 조회는 200입니다. 기존 실제 변환의 404 원인은 아직 확인 중이며, 실제 AI 재검증은 별도 승인을 기다립니다.** 운영자가 Auto confirm으로 일반 회원 계정을 발급하는 방식은 가입용 SMTP가 필요하지 않습니다. 회원 직접 가입·인증메일을 제공할 때만 Custom SMTP를 설정합니다. Google Cloud·Oracle·Cloudflare는 필요하지 않습니다.

## 1. Supabase DB 적용

대상 프로젝트: [Q-Lab BRAIN Alpha Harness](https://supabase.com/dashboard/project/sogpsiheygdwmhdlizvy). 다른 프로젝트에는 적용하지 않습니다.

SQL Editor에서 [회원·사용량 마이그레이션](../supabase/migrations/202609270001_membership.sql)을 실행합니다. 새 private 테이블·승인 함수·사용량 함수를 만들고 기존 Auth 계정도 승인 대기로 등록합니다. 기존 테이블을 삭제하지 않습니다. 같은 마이그레이션은 다시 실행할 수 있습니다.

이어서 [동시 20건·대기열 업그레이드](../supabase/migrations/202609270002_concurrency_queue.sql), [누적 2만 원 비용 제한](../supabase/migrations/202609270003_ai_budget.sql)을 순서대로 실행합니다. 기존 프로젝트에는 아직 적용하지 않은 마이그레이션만 실행하세요. 초기 설치는 001 → 002 → 003 순서입니다. 003을 다시 실행해도 누적 금액을 초기화하지 않습니다. [회원 검색·페이지 조회 004](../supabase/migrations/202609270004_member_pages.sql)는 전체 회원 검색을 위한 선택 업그레이드이며 현재 운영 DB에는 미적용입니다. 로컬 SQL 검증과 배포 승인을 받은 뒤 적용합니다. 미적용 시 앱은 기존 `brain_members()`로 최근 200명 범위에서 조회·필터·페이지 이동과 승인·이용 중지를 지원합니다. 200명에 도달하면 화면에 조회 범위 제한을 안내합니다. 이전에 열린 화면의 배열 응답도 유지합니다.

**적용 완료:** 대상 프로젝트 SQL Editor에서 성공을 확인했습니다. [읽기 전용 검증 SQL](../supabase/verify_membership.sql)로 세 테이블의 RLS 활성화·익명/회원 직접 CRUD 금지, 변환 예약·결과 함수의 서버 전용 실행 권한도 확인했습니다. 최초 운영자의 이메일 인증·approved/admin 상태를 확인했습니다. 003 적용 후 한도 20,000원·누적 0원·익명/일반 회원의 예약 금지·서버 전용 예약 권한도 확인했습니다.

회원 테이블은 브라우저 CRUD를 허용하지 않습니다. 회원 JWT로 자신의 상태 조회 및 운영자 관리 함수만 실행할 수 있고, 변환 예약·결과 저장은 서버 Secret 권한으로만 처리합니다. 회원 정보의 `role`·`status`를 직접 바꾸는 방식은 사용하지 않습니다.

## 2. 이메일 회원가입과 메일 발송

Supabase Authentication에서:

- Email 로그인 켬
- Allow new users to sign up 켬 (실제 저장 완료)
- Confirm email 켬 유지
- 익명 로그인·수동 계정 연결 끔 유지
- Site URL: `https://natural-language-brain-alpha-harness.vercel.app`
- Redirect URLs: `http://127.0.0.1:8080/`, `http://localhost:8080/`; Preview를 검증할 때는 그 주소도 정확히 추가

**Custom SMTP를 먼저 설정해야 일반 회원에게 이메일 인증을 보낼 수 있습니다.** Supabase 기본 메일은 조직의 팀 계정만 대상으로 하며 현재 시간당 2건 제한이 있습니다. 발신 도메인 및 SMTP host·port·user·password·From 주소를 메일 서비스에서 준비해 Authentication의 SMTP 설정에 입력합니다. 비밀번호는 사용자가 직접 입력합니다. [Supabase 공식 SMTP 안내](https://supabase.com/docs/guides/auth/auth-smtp).

가입 후 인증 메일 링크를 열고 사이트에서 이메일·비밀번호로 로그인하면 승인 대기 화면이 나옵니다. 인증 링크만으로 변환 기능이 열리지 않습니다.

**비밀번호:** 앱의 8자 이상 조건은 제거했습니다. 2026-09-27 실제 Email 설정은 최소 6자·문자 조합 요구 없음이므로 숫자로만 된 6자 이상 학번을 사용할 수 있습니다. Supabase 자체가 요구하는 최소 6자는 앱에서 해제할 수 없습니다. 계정을 미리 생성해도 이메일 인증과 운영자 승인 상태를 확인해야 이용할 수 있습니다.

## 3. 첫 운영자

`seungzookim@gmail.com`으로 직접 가입하고 인증 메일을 확인합니다. 비밀번호를 채팅으로 전달하지 않습니다.

그 후 신뢰된 SQL Editor에서 [첫 운영자 설정](../supabase/bootstrap_operator.sql)을 실행합니다. 이메일 인증을 완료한 해당 계정만 approved/admin으로 바꾸며, 계정이 없거나 미인증이면 실행을 중단합니다. 현재 해당 운영자 계정의 이메일 인증과 approved/admin 상태를 실제 Supabase에서 확인했습니다.

운영자로 로그인하면 오른쪽 위 **설정 → 회원 승인 관리**에서 회원 목록과 누적 AI 비용 한도를 확인할 수 있습니다. 일반 회원은 설정 버튼이나 API 키 입력창 없이 서버 공용 키를 사용합니다. 일반 회원의 승인·거절·이용 중지를 처리합니다. 운영자 계정 자체의 권한 변경은 대시보드에서 별도로 관리하며 사이트 버튼으로 변경할 수 없습니다.

## 4. Vercel 환경변수

대상: [natural-language-brain-alpha-harness](https://vercel.com/ksj12/natural-language-brain-alpha-harness), FastAPI 프레임워크, 저장소 루트, Seoul(icn1), 최대 65초. 진입점은 루트 `app.py`, 설정은 `vercel.json`입니다. [Vercel FastAPI 문서](https://vercel.com/docs/frameworks/backend/fastapi).

[환경변수 예시](../.env.vercel.example)를 참고하여 Production에 등록합니다. Preview를 사용할 때는 별도 테스트 Supabase·키를 사용하세요.

| 변수 | 값 |
| --- | --- |
| APP_ENV | production |
| AUTH_MODE | supabase |
| HARNESS_PROVIDER | muse |
| MUSE_API_PROVIDER | meta |
| MUSE_MODEL | meta/muse-spark-1.3-contributor |
| MAX_CONCURRENT_JOBS | 20 |
| MODEL_TIMEOUT_SECONDS | 35 |
| APP_PUBLIC_URL | https://natural-language-brain-alpha-harness.vercel.app |
| SUPABASE_URL | https://sogpsiheygdwmhdlizvy.supabase.co |
| SUPABASE_PUBLISHABLE_KEY | 해당 Supabase 프로젝트 공개 키 |
| SUPABASE_SECRET_KEY | 해당 프로젝트 서버 Secret, 비밀 변수 |
| META_API_KEY 또는 AI_API_KEY | Meta 직접 발급 키, 비밀 변수 |

Chrome에서 `MAX_CONCURRENT_JOBS=20`을 Production·Preview에 저장했습니다. 환경변수는 다음 배포부터 적용됩니다.

Chrome에서 `HARNESS_PROVIDER=muse`, `MUSE_MODEL=meta/muse-spark-1.3-contributor`, timeout 35를 Production·Preview에 저장했습니다. `AUTH_MODE=supabase`와 `APP_PUBLIC_URL`은 Production에 저장했습니다. 미사용 OpenAI 모델 변수는 Muse 변수로 변경했고 OpenAI 키를 등록하지 않았습니다. Preview의 실제 계정 테스트에는 별도 URL·Supabase 설정을 지정하세요. 로컬 설정 창의 키는 Vercel로 자동 이전되지 않습니다. 서버 Secret은 인증·한도 DB 함수에 사용하는 권한이므로 공개 키와 구분하고 브라우저 코드에 넣지 않습니다.

기존 Supabase 서버 키를 `SUPABASE_SECRET_KEY`라는 **Secret 유형·Production 전용** 변수로 저장했고 Vercel 성공 알림을 확인했습니다. 로컬 시험에도 기존 키를 Git에서 제외된 `.env.local`에 저장했습니다. 키를 새로 생성·회전하지 않았습니다.

현재 사용자의 키는 Meta 직접 발급 키입니다. Vercel Production에 `MUSE_API_PROVIDER=meta`와 Secret `META_API_KEY`가 저장돼 있습니다. 저장된 Secret의 원문은 다시 볼 수 없어 로컬 키와의 값 일치는 확인하지 못했지만, 배포 서버의 해당 키로 모델 목록 조회 200을 확인했습니다. 기존 `AI_API_KEY`는 별칭으로 지원하며 명시적인 Meta 키를 우선합니다. Meta 모드는 `META_API_KEY` → `AI_API_KEY`만 읽고 `https://api.meta.ai/v1/chat/completions`에 고정 연결합니다. 모델 식별자는 같은 Contributor 모델의 Meta 표기인 `muse-spark-1.3-contributor`로 전송합니다. [Meta Chat Completions](https://dev.meta.ai/docs/protocols/chat-completions).

Vercel AI Gateway를 따로 선택하려면 `MUSE_API_PROVIDER=gateway`와 Vercel 발급 키를 설정합니다. 이 모드의 키 우선순위는 `AI_GATEWAY_API_KEY` → `AI_API_KEY` → `VERCEL_OIDC_TOKEN`입니다. OIDC는 Meta 직접 인증에 사용할 수 없습니다. [Vercel OIDC 안내](https://vercel.com/docs/ai-gateway/authentication-and-byok/oidc).

두 연결 방식 모두 Contributor 모델만 허용하며 모델·제공자 자동 전환이 없습니다. Contributor 학습 활용 조건에 동의한 변환만 호출합니다. Gateway를 선택한 경우에도 제공자는 Meta만 허용합니다. [Gateway Chat Completions](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions).

## 5. 배포 및 확인

### 재배포 전 빌드 준비 (2026-09-28)

첫 배포 시 `uv lock`이 `No project table found`로 실패했습니다. `pyproject.toml`에 프로젝트 메타데이터와 `requirements.txt`와 동일한 런타임 의존성 4개를 추가하고 `uv.lock`을 생성했습니다. 로컬 Python 3.12의 별도 환경에서 `uv lock`과 `uv sync --locked --no-dev`, `app.py` 로딩을 확인했습니다. 정적 파일 존재와 운영 API 문서 비공개도 확인했으며 이 로컬 빌드 확인에서는 실제 AI 제공자를 초기화하지 않았습니다. 2026-09-28 Chrome에서 Vercel Production `c5f45cd`의 Ready 상태를 확인했습니다.

Vercel의 Ignored Build Step은 `Automatic`으로 저장했으며, 저장소의 `git.deploymentEnabled=false`는 유지합니다. GitHub 수정 반영만으로 재배포하지 않습니다. 재배포 시 기존 실패 배포의 **Redeploy** 대신 **Deployments → Deployments actions → Create Deployment → main**에서 새 수정 커밋을 확인하고 **Deploy to Production**을 선택하세요. SQL 004는 운영 DB에 적용하지 않았습니다.

초기에는 **Ignored Build Step: Don’t build anything (`exit 0`)**으로 배포를 중지했습니다. 승인된 수동 배포를 위해 현재는 `Automatic`으로 변경했습니다. 저장소의 `vercel.json`에는 `git.deploymentEnabled=false`를 유지하여 모든 브랜치의 Git 자동 배포를 차단합니다. GitHub 코드 저장과 수동 웹사이트 배포는 별개입니다. [Vercel Git 배포 설정](https://vercel.com/docs/project-configuration/git-configuration#turning-off-all-automatic-deployments).

환경변수·DB와 검증 결과를 확인한 후 **재배포 직전에 운영자 승인을 받습니다.** 진단 버전 `896e2be`는 2026-09-28 운영자 승인 후 배포됐으며 Production Current와 기본 도메인 적용을 확인했습니다. 향후 자동 배포를 원할 때 `git.deploymentEnabled`를 `true`로 변경하며, 수동 배포 승인과 향후 자동 배포 허용은 별개입니다. 회원 계정 발급→운영자 승인→로그인→단순 전략 한 번 변환→이용 중지 차단을 확인합니다. 실제 유료 AI 변환은 사용자가 별도로 승인한 경우에만 실행합니다. BRAIN Simulate는 사용자가 별도로 실행합니다.

## 배포 후 Meta 404 진단 (2026-09-28)

Chrome에서 Production `c5f45cd`의 Ready 상태와 실제 `/api/convert` 요청 2건의
Meta `POST /v1/chat/completions` 404를 확인했습니다. Supabase 인증·승인·한도 조회는
정상이며, 연결 방식은 `meta`, 고정 모델은 `meta/muse-spark-1.3-contributor`입니다.
같은 날 로컬에 저장된 키의 `GET /v1/models`는 200으로 Contributor 모델을 반환했습니다.
이 모델 목록 조회는 전략이나 프롬프트를 보내지 않으며 AI 생성을 하지 않습니다.
서버 키의 실제 값 일치 여부와 배포 서버에서의 모델 접근 여부는 아직 확정하지 않았습니다.

진단 코드를 배포한 뒤 운영자로 로그인한 Chrome에서
`/api/admin/provider-check`를 열어 **배포 서버의** Meta 모델 목록을 확인할 수 있습니다.
이 경로는 승인된 관리자만 접근할 수 있고, 키·원문 오류·다른 모델 목록을 반환하지 않습니다.
변환 횟수·예산을 예약하지 않으며 자동 재시도나 실제 AI 생성도 하지 않습니다.
`httpStatus=200`과 `modelAvailable=true`면 해당 서버 키의 모델 목록에 Contributor가 포함됨을 확인합니다. 실제 생성 성공은 별도 검증이 필요합니다.
실제 변환 로그에는 HTTP 상태·허용 목록에 포함된 공급자 오류 코드·응답 종류만 남깁니다.
일반 404와 명시적 `model_not_found`를 구분하며 비밀키·전략·원문 오류는 기록하지 않습니다.

2026-09-28 09:30 KST 운영자 세션의 진단 요청이 배포 서버까지 도달했고, Vercel 로그에서 Meta `GET /v1/models` 200과 진단 경로 200을 확인했습니다. Chrome은 응답 화면을 `ERR_BLOCKED_BY_CLIENT`로 표시해 `modelAvailable` 값은 읽지 못했습니다. 따라서 키의 모델 목록 조회 인증·네트워크 연결은 확인했지만 Contributor 생성 권한이나 실제 생성 성공은 아직 확인한 것이 아닙니다. 미인증 별도 GET은 401로 차단됐습니다.

진단 변경은 로컬 Python 테스트 297개 통과·SQL 관련 30개 건너뜀, 린트 통과를 확인했습니다. GitHub CI는 backend(PostgreSQL 포함)·frontend·gateway 모두 통과했습니다. 이번 변경은 DB 마이그레이션을 요구하지 않습니다. 진단 코드 배포는 승인 후 완료했으며, 실제 AI 검증은 별도 운영자 승인을 기다립니다.

## 월 비용과 상시 운영

[모델 검증 범위·월 1,000회 비용 계산](MODEL_COST_AND_VALIDATION.md)을 참고하세요. AI 토큰 사용료와 호스팅·메일·도메인 비용은 별개입니다. Supabase Free는 1주간 활동이 없으면 일시 정지하므로 세션을 쉬는 기간에는 재개가 필요할 수 있습니다. 중단 없이 유지하려면 Pro(기본 $25/월) 등 운영 조건을 검토하세요. 유료 업그레이드는 하지 않았습니다. [Supabase 요금](https://supabase.com/pricing).

## 사용 제한과 보관

회원별 월 50회·일 20회·분당 2회, 사이트 전체 월 1,000회·동시 20건입니다. 20건을 넘으면 Supabase 대기열에 요청 ID·입력 해시만 보관합니다. 열린 화면에서 5초마다 같은 ID·입력으로 원자적 처리 슬롯을 확보하고, 순서가 오면 실제 변환을 한 번 시작합니다. 처리 중인 요청은 결과 조회만 합니다. 별도 상주 서버·백그라운드 워커·유료 큐 서비스는 필요하지 않습니다.

대기 최대 10분이며 화면을 닫거나 연결이 끊겨 2분간 확인하지 않은 대기 요청은 만료됩니다. 화면을 닫은 뒤에도 자동 처리하는 기능은 없습니다. 대기열 입장 때 사용량을 한 번 예약하므로 취소·만료된 대기도 회원/사이트 요청 한도에 포함하지만 AI 비용은 발생하지 않습니다. 월·일·분당 한도 초과는 대기열로 넘기지 않고 거절합니다.

추가로 실제 Muse 시도 전에 4원씩 누적 예약하고 20,000원에서 새 유료 호출을 차단합니다. DB 오류에도 호출하지 않으며 월 변경·회원 삭제로 금액을 초기화하지 않습니다. 운영자 설정에서 확인합니다. 실제 청구서·다른 앱 비용을 제한하는 기능은 아니며 [예산 계산과 범위](AI_BUDGET.md)를 확인하세요.

한국 시간 기준 일·월 경계를 사용합니다. 실패한 시도도 예약 횟수에 포함합니다. 변경하려면 마이그레이션 함수 및 사용량 표시의 상수를 함께 수정합니다.

동일 사용자·입력·요청 ID의 완료 결과는 24시간 이내 재사용합니다. 조회는 본인만 가능합니다. 오래된 결과는 새 예약 때 정리하고, 한도 계산용 요청 메타데이터는 최대 35일 정리 대상입니다. 별도 예약 작업이 없으므로 24시간이 지나자마자 자동 삭제된다는 보장은 없습니다. 추가 장기 보관이 필요하면 별도 정책을 정하세요.
