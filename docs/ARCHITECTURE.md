# 현재 구조 (2026-09-29)

브라우저 → Vercel FastAPI → Supabase 신원·승인 확인 → 작업/예산 예약 → OpenAI GPT 1회 → Python 검사·컴파일 → FASTEXPR + 12개 설정.

## 모델 정책과 연결

`openai_policy.py`는 GPT-5.4 mini·`none`·일반/캐시 입력과 출력 단가를 관리합니다. 출력은 1,024토큰, 직렬화 요청은 16,000바이트로 제한합니다. 추론·출력 상한은 `frozen=True`, `init=False` 필드이며 요청·환경변수로 올릴 수 없습니다.

`provider_config.py`는 OpenAI 키와 고정 엔드포인트를 결정합니다. `OPENAI_API_KEY`만 읽습니다. 타임아웃은 최대 35초입니다. 모델이 고정 정책과 다르면 호출 전에 차단합니다.

`chat_provider.py`는 한 번의 HTTP 생성 요청·응답 검사·오류 처리를 공유합니다. `openai_provider.py`는 OpenAI의 모델·캐시 비용·읽기 전용 진단을 담당하고 `provider.py`는 공급자를 조립합니다. 구조화 출력 스키마는 `response_schema.py`, 개발용 mock은 `mock_provider.py`, 결과 형식은 `provider_types.py`에 있습니다. 운영 환경에서는 mock을 차단합니다. 자동 재시도·대체 모델 호출은 없습니다.

## 해석과 생성

`backend/app/skills/brain-strategy/SKILL.md`의 본문이 모델 시스템 지침입니다. 모델은 StrategyIR JSON을 반환하며 `service.py`가 원문 조건을 검사하고 `compiler.py`가 최종 FASTEXPR을 생성합니다. confidence는 기존 응답과의 호환성을 위한 null 필드입니다.

`hypotheses.py`는 모멘텀·반전 가설, 관찰 기간, 주/월 환산과 기본값 규칙을 검사합니다. `SignalIR.operation=return`은 종가 비율로 기간 수익률을 계산하며 기존 절대 변화량 `delta`와 구분합니다. 검증을 통과한 IR에서 `strategy_guidance.py`가 자연어 설명·가정·개선 실험·수정 선택지를 생성합니다. 이 단계에는 추가 모델 호출이 없습니다. 실패 결과에는 성공한 전략처럼 보이는 설명이나 제안을 붙이지 않습니다.

`view.js`의 수정 선택지는 `form.js`의 입력과 설정만 갱신합니다. 사용자가 다시 변환할 때 새 요청이 발생하며, 화면에는 기존 결과가 변경 전 전략임을 표시합니다. 폼에 노출되지 않는 Test Period·NaN 설정 등도 보존하고 로그아웃 시 초안과 함께 삭제합니다. 기존 DB 캐시에는 새 응답 필드가 없어도 기본 빈 값으로 읽을 수 있습니다.

## 인증과 권한

FastAPI가 Supabase password Auth를 중계하고 access/refresh 토큰을 HttpOnly 쿠키에 담습니다. API마다 원격 getUser와 DB 함수로 승인·역할을 검사합니다. 가입 metadata는 권한으로 신뢰하지 않습니다. approved 회원만 변환하고 approved/admin만 회원 관리·연결 진단을 수행합니다.

`AUTH_MODE`는 `supabase` 또는 개발용 `none`만 허용합니다. 운영에서 `none`을 차단합니다. 개발용 키 변경·무인증 변환은 loopback 클라이언트·호스트·Origin을 확인합니다.

## 작업·대기열·비용

`conversion.py`의 `ConversionCoordinator`가 HTTP 요청 이후의 변환 흐름을 조정합니다. `MemberJob`이 동일한 요청 ID·입력 해시로 슬롯 예약·예산 예약·결과 저장을 수행합니다. 슬롯을 실제 획득한 요청만 실패 또는 완료를 기록합니다.

DB는 전역 잠금으로 승인·쿼터·실행 슬롯을 원자적으로 확인합니다. 실행 슬롯은 20개이며 초과 요청은 대기합니다. 브라우저는 5초 간격으로 같은 ID/본문을 재확인하고 실행 중인 요청은 읽기 전용 결과 조회만 합니다. 대기는 2분 뒤 만료되고 전체 최대 대기 시간은 10분입니다. 동일 요청의 결과는 24시간 재사용합니다.

유료 생성 전에 누적 예산을 예약합니다. 004 마이그레이션 이후 새 요청은 34원을 예약하며 과거 누적액과 예약 기록을 유지합니다. 실패·월 변경·회원 삭제로 초기화하지 않습니다. 공급자 실제 청구액과 앱 예약액의 차이는 [AI_BUDGET.md](AI_BUDGET.md)를 따릅니다.

## 프런트엔드와 배포

API 요청·세션·대기 상태는 `api.js`, 모델 연결 상태는 `provider.js`, 회원/운영자 화면은 `membership.js`가 소유합니다. 대시보드는 메서드를 통해 상태를 변경합니다. 현재 서버가 제공하지 않는 이전 `/api/admin/usage` 패널은 제거했습니다.

현재 배포 경로는 `app.py`와 `vercel.json`이며 `scripts/deploy_openai.py`가 검증·환경변수 등록·배포 후 확인을 묶습니다. [OpenAI 배포 준비](OPENAI_DEPLOYMENT.md)를 따릅니다. Cloudflare Worker·Cloud Run 배포 스크립트·HMAC 인증과 해당 CI는 제거했으며 Git 이력에서 확인할 수 있습니다. 실제 호출 경로는 OpenAI뿐입니다.
