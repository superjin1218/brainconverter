# Vercel + Supabase 회원 사이트 설정

2026-09-27 기준. **실제 Supabase DB·가입 설정과 Vercel Production 서버 Secret 저장까지 완료했습니다. 배포·실제 Muse 호출은 아직 하지 않았습니다.** 아래는 현재 변경을 운영에 연결하는 순서입니다. Google Cloud·Oracle·Cloudflare는 필요하지 않습니다.

## 1. Supabase DB 적용

대상 프로젝트: [Q-Lab BRAIN Alpha Harness](https://supabase.com/dashboard/project/sogpsiheygdwmhdlizvy). 다른 프로젝트에는 적용하지 않습니다.

SQL Editor에서 [회원·사용량 마이그레이션](../supabase/migrations/202609270001_membership.sql)을 실행합니다. 새 private 테이블·승인 함수·사용량 함수를 만들고 기존 Auth 계정도 승인 대기로 등록합니다. 기존 테이블을 삭제하지 않습니다. 같은 마이그레이션은 다시 실행할 수 있습니다.

**적용 완료:** 대상 프로젝트 SQL Editor에서 성공을 확인했습니다. [읽기 전용 검증 SQL](../supabase/verify_membership.sql)로 세 테이블의 RLS 활성화·익명/회원 직접 CRUD 금지, 변환 예약·결과 함수의 서버 전용 실행 권한도 확인했습니다. 현재 계정·승인 회원·운영자는 모두 0명입니다.

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

그 후 신뢰된 SQL Editor에서 [첫 운영자 설정](../supabase/bootstrap_operator.sql)을 실행합니다. 이메일 인증을 완료한 해당 계정만 approved/admin으로 바꾸며, 계정이 없거나 미인증이면 실행을 중단합니다. 현재는 운영자 계정 생성·권한 부여를 아직 하지 않았습니다.

운영자로 로그인하면 **회원 승인 관리**가 표시됩니다. 일반 회원의 승인·거절·이용 중지를 처리합니다. 운영자 계정 자체의 권한 변경은 대시보드에서 별도로 관리하며 사이트 버튼으로 변경할 수 없습니다.

## 4. Vercel 환경변수

대상: [natural-language-brain-alpha-harness](https://vercel.com/ksj12/natural-language-brain-alpha-harness), FastAPI 프레임워크, 저장소 루트, Seoul(icn1), 최대 65초. 진입점은 루트 `app.py`, 설정은 `vercel.json`입니다. [Vercel FastAPI 문서](https://vercel.com/docs/frameworks/backend/fastapi).

[환경변수 예시](../.env.vercel.example)를 참고하여 Production에 등록합니다. Preview를 사용할 때는 별도 테스트 Supabase·키를 사용하세요.

| 변수 | 값 |
| --- | --- |
| APP_ENV | production |
| AUTH_MODE | supabase |
| HARNESS_PROVIDER | muse |
| MUSE_MODEL | meta/muse-spark-1.3-contributor |
| MAX_CONCURRENT_JOBS | 2 |
| MODEL_TIMEOUT_SECONDS | 35 |
| APP_PUBLIC_URL | https://natural-language-brain-alpha-harness.vercel.app |
| SUPABASE_URL | https://sogpsiheygdwmhdlizvy.supabase.co |
| SUPABASE_PUBLISHABLE_KEY | 해당 Supabase 프로젝트 공개 키 |
| SUPABASE_SECRET_KEY | 해당 프로젝트 서버 Secret, 비밀 변수 |
| AI_GATEWAY_API_KEY | 새 Vercel AI Gateway 키, 비밀 변수 |

Chrome에서 `HARNESS_PROVIDER=muse`, `MUSE_MODEL=meta/muse-spark-1.3-contributor`, timeout 35를 Production·Preview에 저장했습니다. `AUTH_MODE=supabase`와 `APP_PUBLIC_URL`은 Production에 저장했습니다. 미사용 OpenAI 모델 변수는 Muse 변수로 변경했고 OpenAI 키를 등록하지 않았습니다. Preview의 실제 계정 테스트에는 별도 URL·Supabase 설정을 지정하세요. 로컬 설정 창의 키는 Vercel로 자동 이전되지 않습니다. 서버 Secret은 인증·한도 DB 함수에 사용하는 권한이므로 공개 키와 구분하고 브라우저 코드에 넣지 않습니다.

기존 Supabase 서버 키를 `SUPABASE_SECRET_KEY`라는 **Secret 유형·Production 전용** 변수로 저장했고 Vercel 성공 알림을 확인했습니다. 키를 새로 생성·회전하지 않았으며 로컬 파일에는 저장하지 않았습니다.

Vercel 배포에서는 자동 제공되는 `VERCEL_OIDC_TOKEN`으로 AI Gateway에 인증할 수도 있으므로 `AI_GATEWAY_API_KEY`가 반드시 필요한 것은 아닙니다. 프로그램은 명시적인 Gateway 키가 있으면 우선 사용하고, 없으면 OIDC를 사용합니다. OIDC를 실제 배포에서 확인하거나 별도 Gateway 키를 준비하고, 모델 사용 권한·크레딧을 확인해야 합니다. 로컬 실사용에는 Gateway 키가 필요합니다. [Vercel OIDC 안내](https://vercel.com/docs/ai-gateway/authentication-and-byok/oidc).

Muse 요청은 Gateway에서 Meta 제공자만 허용하며 모델·제공자 자동 전환이 없습니다. Contributor 학습 활용 조건에 동의한 변환만 호출합니다. [Gateway Chat Completions](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions).

## 5. 배포 및 확인

현재 **Ignored Build Step: Don’t build anything (`exit 0`)**이며 실제 배포가 없습니다. 저장소의 `vercel.json`에도 `git.deploymentEnabled=false`를 설정하여 모든 브랜치의 Git 자동 배포를 차단합니다. GitHub 코드 저장과 웹사이트 배포는 별개이며 배포 허용 전까지 두 중지 설정을 유지합니다. [Vercel Git 배포 설정](https://vercel.com/docs/project-configuration/git-configuration#turning-off-all-automatic-deployments).

배포할 때 환경변수·SMTP·DB를 모두 완료한 후 `git.deploymentEnabled`를 `true`로 변경하고 자동 빌드 중지 설정을 해제한 뒤 최초 배포합니다. 가입→인증→승인 대기→운영자 승인→단순 전략 한 번 변환→이용 중지 차단을 확인합니다. 실제 유료 변환은 새 모델 키와 크레딧을 준비한 후 한 건부터 확인합니다. BRAIN Simulate는 사용자가 별도로 실행합니다.

## 월 비용과 상시 운영

[모델 검증 범위·월 1,000회 비용 계산](MODEL_COST_AND_VALIDATION.md)을 참고하세요. AI 토큰 사용료와 호스팅·메일·도메인 비용은 별개입니다. Supabase Free는 1주간 활동이 없으면 일시 정지하므로 세션을 쉬는 기간에는 재개가 필요할 수 있습니다. 중단 없이 유지하려면 Pro(기본 $25/월) 등 운영 조건을 검토하세요. 유료 업그레이드는 하지 않았습니다. [Supabase 요금](https://supabase.com/pricing).

## 사용 제한과 보관

회원별 월 50회·일 20회·분당 2회, 사이트 전체 월 1,000회·동시 2건입니다. 한국 시간 기준 일·월 경계를 사용합니다. 실패한 시도도 예약 횟수에 포함합니다. 변경하려면 마이그레이션 함수 및 사용량 표시의 상수를 함께 수정합니다.

동일 사용자·입력·요청 ID의 완료 결과는 24시간 이내 재사용합니다. 조회는 본인만 가능합니다. 오래된 결과는 새 예약 때 정리하고, 한도 계산용 요청 메타데이터는 최대 35일 정리 대상입니다. 별도 예약 작업이 없으므로 24시간이 지나자마자 자동 삭제된다는 보장은 없습니다. 추가 장기 보관이 필요하면 별도 정책을 정하세요.
