# 로컬 실행과 공용 AI 키

## 비용 없는 화면 확인

처음 한 번 `make install`, 이후 `make dev`를 실행하고 <http://127.0.0.1:8080>에 접속합니다. 같은 포트에서 다른 서버가 켜져 있으면 해당 터미널에서 Ctrl+C로 종료하세요.

이 명령은 Supabase 회원 로그인 모드와 **모의 모델**을 사용합니다. 로그인 전에는 로그인/회원가입, 미승인 상태에는 승인 대기, 승인된 회원에게는 변환 화면이 나옵니다. 모의 결과는 AI 품질 검증이 아닙니다.

Git에서 제외된 `.env.local`에 Supabase URL·공개 키와 서버 Secret·AI 키를 설정했습니다. 파일 권한은 소유자만 읽고 쓸 수 있는 `0600`입니다. 다른 컴퓨터에서는 [설정 예시](../.env.local.example)를 참고해 직접 설정해야 합니다.

2026-09-27 실제 로컬 확인: Meta 키를 Vercel Gateway에 보내던 인증 오류를 수정했습니다. `make dev-ai`에서 승인된 관리자 로그인 → Meta Contributor 단순 전략 및 거래량 조건 전략 **2건 성공**을 확인했습니다. 초기 인증 실패 1회를 포함해 사용량 3회·보수적 예산 12원이며 실제 공급자 청구액과 다릅니다. BRAIN 시뮬레이션은 실행하지 않았습니다.

## 실제 회원 변환

회원 모드에는 키 입력창이 없습니다. 일반 회원은 설정 버튼도 보지 않으며 서버 공용 키를 사용합니다. 운영자 설정에서는 연결 여부·회원 승인·누적 비용을 확인합니다.

1. Supabase에 마이그레이션 001 → 002 → 003을 적용합니다. 현재 Q-Lab 프로젝트에는 모두 적용했습니다.
2. `.env.local`에 `SUPABASE_SECRET_KEY`, `MUSE_API_PROVIDER=meta`, Meta 발급 키 `META_API_KEY`를 설정합니다. `AI_API_KEY`도 별칭으로 인식합니다. 현재 로컬에는 설정을 완료했습니다.
3. 기존 서버를 종료하고 `make dev-ai`로 시작합니다.
4. <http://127.0.0.1:8080>에서 승인된 계정으로 로그인합니다.
5. Contributor 학습 활용 안내에 동의하고 간단한 전략 한 건을 변환합니다. 이 단계부터 유료 요청이 발생할 수 있습니다.

키는 채팅·명령 기록·Git에 남기지 마세요. 파일 수정 후 서버를 재시작하면 적용됩니다. Vercel의 환경변수는 로컬 컴퓨터로 내려오지 않습니다.

연결 방식은 서버의 `MUSE_API_PROVIDER`로 고정하며 자동 전환하지 않습니다. `meta`는 [Meta 공식 API](https://dev.meta.ai/docs/protocols/chat-completions)를 직접 사용하고 `META_API_KEY` → `AI_API_KEY` 순으로 읽습니다. `gateway`(미지정 시 기본값)는 [Vercel AI Gateway](https://vercel.com/docs/ai-gateway/authentication-and-byok/authentication)를 사용하고 `AI_GATEWAY_API_KEY` → `AI_API_KEY` → `VERCEL_OIDC_TOKEN` 순으로 읽습니다. **서로 다른 발급처의 키를 혼용하지 마세요.** Meta 모드에서는 Gateway 키나 OIDC로 대체하지 않습니다. 연결 표시 자체는 키 저장 여부입니다.

모델은 `meta/muse-spark-1.3-contributor`로 고정하며 출력 최대 1,024토큰, 실패 시 자동 재호출·모델 전환 없음입니다. 회원 변환에는 [누적 2만 원 제한](AI_BUDGET.md)이 적용됩니다.

## 배포 사이트

Vercel Production에 `MUSE_API_PROVIDER=meta`를 저장했습니다. 기존 Secret `AI_API_KEY`를 자동으로 읽습니다. **저장한 환경변수와 수정 코드는 다음 배포부터 적용**되며 현재 배포는 하지 않았습니다. 브라우저에는 키 값을 전달하지 않습니다. 배포 직전 운영자 승인이 필요합니다.

운영자는 **설정 → 회원 승인 관리**에서 회원을 관리합니다. 일반 회원의 이메일 인증에는 Custom SMTP가 필요합니다. [설정 문서](VERCEL_SUPABASE_SETUP.md)를 따르세요.

## 로그인 없는 개발 모드

`make dev-mock`에서만 로컬 설정 창의 메모리 키 연결을 사용할 수 있습니다. 연결한 키는 서버 재시작·연결 해제로 지워집니다. 이 모드는 회원 DB와 누적 금액 제한을 사용하지 않으므로 운영에 사용하지 않습니다. loopback·Host·Origin·요청 헤더를 확인하며 Vercel과 운영 환경에서는 차단합니다.

## 결과의 의미

FASTEXPR와 12개 설정을 생성하고 원문의 조건 보존을 검사합니다. 수익률·성과를 계산하거나 BRAIN에서 시뮬레이션하지 않습니다. 결과를 BRAIN에 옮겨 Simulate로 실행 여부와 성과를 별도로 확인하세요. [오프라인 평가](../evals/README.md)는 실제 모델 품질 검증이 아니며 기본 실행에 유료 평가는 포함하지 않습니다.
