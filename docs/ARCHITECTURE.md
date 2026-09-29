# 현재 구조 (2026-09-29)

브라우저 → Vercel FastAPI → Supabase 신원·승인 확인 → 작업/예산 예약 → OpenAI GPT 1회 → Python 검사·컴파일 → FASTEXPR + 12개 설정.

## 모델 정책과 연결

`openai_policy.py`는 GPT-5.4 mini·`none`·일반/캐시 입력과 출력 단가를 관리합니다. 출력은 1,024토큰, 직렬화 요청은 16,000바이트로 제한합니다. 추론·출력 상한은 `frozen=True`, `init=False` 필드이며 요청·환경변수로 올릴 수 없습니다.

`provider_config.py`는 OpenAI 키와 고정 엔드포인트를 결정합니다. `OPENAI_API_KEY`만 읽습니다. 타임아웃은 최대 35초입니다. 모델이 고정 정책과 다르면 호출 전에 차단합니다.

`chat_provider.py`는 한 번의 HTTP 생성 요청·응답 검사·오류 처리를 공유합니다. `openai_provider.py`는 OpenAI의 모델·캐시 비용·읽기 전용 진단을 담당하고 `provider.py`는 공급자를 조립합니다. 구조화 출력 스키마는 `response_schema.py`, 개발용 mock은 `mock_provider.py`, 결과 형식은 `provider_types.py`에 있습니다. 운영 환경에서는 mock을 차단합니다. 자동 재시도·대체 모델 호출은 없습니다.

## 해석과 생성

`backend/app/skills/brain-strategy/SKILL.md`가 실제 모델의 시스템 지침입니다. 새 요청은 `DraftIR(schemaVersion="draft-v2")`을 반환합니다. AI는 가설에서 측정 방법·누락 기간·점수 조합을 설계하고 가정·개선 실험·서로 다른 수정 선택지를 같은 응답에 포함합니다. 운영 해석은 모멘텀·반전 키워드로 분기하지 않습니다.

`draft_compiler.py`는 식을 Python AST로 파싱하되 실행하지 않습니다. 허용된 데이터·연산·함수와 인자 종류, 양수 관찰 기간, 중첩·노드 수를 검사해 FASTEXPR을 출력합니다. 속성 접근·첨자·임의 함수·실행 구문은 허용하지 않습니다. 자연어 계산 설명과 연산 대응표도 파싱한 식에서 만듭니다. 추가 모델 호출은 없습니다. 원문 숫자와 일부 명시 조건 검사는 의미의 전면적인 증명이 아니며 이를 UI에서 ‘명시 조건 검사’로 표시합니다.

기존 `StrategyIR`/`compiler.py`/`hypotheses.py`/`strategy_guidance.py` 경로는 오프라인 mock과 기존 응답 호환용입니다. 운영 응답 스키마는 새 `DraftIR`만 요청하며, 새 경로가 실패해도 기존 템플릿으로 대체하지 않습니다. confidence는 호환성을 위한 null입니다.

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
