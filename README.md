# 자연어 → WorldQuant BRAIN 코드 웹사이트

자연어 전략을 FASTEXPR 초안과 BRAIN 설정 12개로 변환합니다. 웹사이트는 Vercel, 회원가입·승인·사용량 DB는 Supabase를 사용합니다. 별도 Google Cloud·Oracle·Cloudflare 서버가 필요하지 않습니다.

AI는 **Muse Spark 1.3 Contributor**로 고정했습니다. 변환 규칙을 담은 [SKILL.md](backend/app/skills/brain-strategy/SKILL.md)를 시스템 지침으로 읽어 **한 번** 해석합니다. Python이 구조·원문 조건을 검사하고 허용된 FASTEXPR를 생성합니다. 여러 에이전트의 합의나 자동 모델 재시도는 사용하지 않습니다.

## 먼저 볼 문서

- 로컬 실행·키 연결: [LOCAL_TEST.md](docs/LOCAL_TEST.md)
- Vercel·Supabase 회원 사이트 설정: [VERCEL_SUPABASE_SETUP.md](docs/VERCEL_SUPABASE_SETUP.md)
- 완료한 검증과 아직 남은 작업: [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
- 모델 검증 범위·월 1,000회 비용: [MODEL_COST_AND_VALIDATION.md](docs/MODEL_COST_AND_VALIDATION.md)
- 푸시 전 코드 검토·검증 기록: [CODE_REVIEW.md](docs/CODE_REVIEW.md)

이 버전은 배포 전 준비 단계입니다. `vercel.json`의 `git.deploymentEnabled=false`로 Git 푸시에 따른 자동 배포를 차단합니다. 실제 배포는 아직 하지 않았으며, 새 모델의 실제 API 및 실제 Supabase 가입 흐름은 계정 설정을 마친 후 확인해야 합니다.

## 회원 이용 흐름

회원가입 → 이메일 인증 → 로그인 → 운영자 승인 대기 → 승인 후 전략 변환.

운영자는 사이트의 회원 관리 화면에서 승인·거절·이용 중지를 처리합니다. 최초 운영자는 `seungzookim@gmail.com`이며, 그 계정의 이메일 인증 후 신뢰된 Supabase SQL Editor에서만 운영자 권한을 설정합니다. 회원가입 폼의 값으로 승인·운영자 권한을 부여할 수 없습니다.

인증 토큰은 HttpOnly 쿠키에 보관합니다. 서버는 Supabase에서 로그인 신원을 확인하고 DB의 승인 상태를 검사합니다. 모델 키와 Supabase 서버 키는 Vercel Secret에만 설정하며 회원에게 노출하지 않습니다.

앱은 비밀번호의 최소 길이·특수문자·영문 조합을 요구하지 않습니다. Supabase 프로젝트의 현재 규칙은 최소 6자이며 문자 조합 요구가 없어 6자 이상 숫자 학번을 사용할 수 있습니다. 실제 회원 계정은 운영자가 별도로 준비합니다.

## 비용 제한

- 변환당 AI 요청 1회, 출력 최대 1,024토큰, 다른 모델로 자동 전환 없음
- 회원별 분당 2회·하루 20회·월 50회, 사이트 전체 월 1,000회·동시 2건
- 동일 요청 ID는 24시간 이내 저장된 결과를 재사용
- 제한은 PostgreSQL에서 원자적으로 적용; 실패한 시도도 사용 횟수에 포함

Contributor는 입력과 응답을 Meta의 모델 학습에 사용하는 조건이 있습니다. 변환 화면에서 안내하고 동의를 받아야 실제 모델을 호출합니다. [Meta 조건·요금](https://dev.meta.ai/docs/pricing-rate-limits), [Vercel 모델](https://vercel.com/ai-gateway/models/muse-spark-1.3-contributor).

## 로컬 실행

```bash
make install
make dev
```

<http://127.0.0.1:8080>에서 확인합니다. 기본 실행은 회원 로그인 화면부터 표시하며 `.env.local`의 Supabase 설정을 읽습니다. 승인된 회원만 변환 화면을 볼 수 있습니다. AI는 키 연결 전까지 비용 없는 모의 모드입니다. 로그인 없이 코드 화면만 보는 개발 실행은 `make dev-mock`이며 실제 키 연결은 LOCAL_TEST 문서를 따릅니다.

```bash
make test
make lint
make test-frontend
make test-sql   # Docker 필요; 외부 Supabase에 연결하지 않는 임시 PostgreSQL 테스트
```

## 지원 범위와 결과 해석

가격·수익률 순위, 일정 기간 가격 변화, 평균 거래량 필터, 중립화 설정 등 현재 스키마의 단일 신호를 지원합니다. 복합 신호·재무 데이터·손절·익절 등은 지원하지 않으며 조건이 소실되면 거절합니다.

PASS는 내부 변환 검사 통과입니다. 전략의 수익성이나 BRAIN 실행 성공을 뜻하지 않습니다. BRAIN 로그인·Simulate·Alpha 제출은 자동 실행하지 않습니다. 생성 결과와 설정을 BRAIN에 옮겨 직접 실행해야 합니다.

기본 설정: FASTEXPR / EQUITY / USA / TOP3000 / Delay 1 / Neutralization SUBINDUSTRY / Decay 4 / Truncation 0.08 / Pasteurization ON / Unit Handling VERIFY / NaN Handling OFF / Test Period 0 years·0 months. 명시한 설정을 우선하고 빠진 값만 기본값으로 채웁니다.

`gateway/`와 Cloud Run 관련 파일은 이전 배포 방식의 기록입니다. 새 회원 사이트 설정에는 사용하지 않습니다.
