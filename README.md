# 자연어 → WorldQuant BRAIN 코드 웹사이트

자연어 전략을 FASTEXPR 초안과 BRAIN 설정 12개로 변환합니다. 웹사이트는 Vercel, 회원가입·승인·사용량 DB는 Supabase를 사용합니다. 별도 Google Cloud·Oracle·Cloudflare 서버가 필요하지 않습니다.

AI는 **Muse Spark 1.3 Contributor**로 고정했습니다. 변환 규칙을 담은 [SKILL.md](backend/app/skills/brain-strategy/SKILL.md)를 시스템 지침으로 읽어 **한 번** 해석합니다. Python이 구조·원문 조건을 검사하고 허용된 FASTEXPR를 생성합니다. 여러 에이전트의 합의나 자동 모델 재시도는 사용하지 않습니다.

## 먼저 볼 문서

- 로컬 실행·키 연결: [LOCAL_TEST.md](docs/LOCAL_TEST.md)
- Vercel·Supabase 회원 사이트 설정: [VERCEL_SUPABASE_SETUP.md](docs/VERCEL_SUPABASE_SETUP.md)
- 완료한 검증과 아직 남은 작업: [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
- 모델 검증 범위·월 1,000회 비용: [MODEL_COST_AND_VALIDATION.md](docs/MODEL_COST_AND_VALIDATION.md)
- 누적 2만 원 자동 중지: [AI_BUDGET.md](docs/AI_BUDGET.md)
- 배포 후 변환 실패 조사·같은 저가 모델 연결 대안: [DEPLOYED_CONVERSION_RECOVERY.md](docs/DEPLOYED_CONVERSION_RECOVERY.md)
- 푸시 전 코드 검토·검증 기록: [CODE_REVIEW.md](docs/CODE_REVIEW.md)

2026-09-28 운영자 승인 후 진단 버전 `2ed26fa`를 Vercel Production에 배포했습니다. 로컬 **Meta Contributor 실제 코드 생성 3회 성공**을 확인했지만, 배포 서버의 승인받은 변환 1회는 `404 / model_not_found`로 실패했습니다. 서버와 로컬 키는 같고 서버 모델 목록에서만 Contributor가 누락됩니다. **배포 서버의 모델 접근 문제·심층 보안검사·Meta 과금 표시 불일치 확인은 미완료**입니다. [배포 진단과 문의 초안](docs/META_SERVER_MODEL_ACCESS_REPORT.md)을 참고하세요. `vercel.json`의 `git.deploymentEnabled=false`로 Git 푸시에 따른 자동 배포를 차단하며, 후속 재배포와 추가 실제 AI 요청은 각각 운영자 승인을 받습니다.

## 회원 이용 흐름

현재 운영 방식은 **운영자가 Supabase에서 이메일·비밀번호를 지정해 일반 회원 생성(Auto confirm user) → 사이트에서 승인 → 회원 로그인·전략 변환**입니다. 이 방식에는 가입 인증메일용 SMTP가 필요하지 않습니다. 사이트의 직접 회원가입 기능도 코드에 남아 있으며, 회원이 직접 가입하는 방식을 운영하려면 이메일 인증·SMTP 설정을 별도로 확인해야 합니다.

운영자는 **설정 → 회원 승인 관리**에서 승인·거절·이용 중지를 처리합니다. 일반 회원에게 설정 버튼·키 입력창·남은 횟수 표시는 숨기며 서버 공용 키를 자동으로 사용합니다. 사용 한도는 서버에서 그대로 적용합니다. 최초 운영자 `seungzookim@gmail.com`의 이메일 인증·approved/admin 상태를 실제 Supabase에서 확인했습니다. 회원가입 폼의 값으로 승인·운영자 권한을 부여할 수 없습니다.

인증 토큰은 HttpOnly 쿠키에 보관합니다. 서버는 Supabase에서 로그인 신원을 확인하고 DB의 승인 상태를 검사합니다. 모델 키와 Supabase 서버 키는 배포 시 Vercel Secret, 로컬 시험 시 Git에서 제외된 `.env.local`에만 설정하며 회원에게 노출하지 않습니다.

앱은 비밀번호의 최소 길이·특수문자·영문 조합을 요구하지 않습니다. Supabase 프로젝트의 현재 규칙은 최소 6자이며 문자 조합 요구가 없어 6자 이상 숫자 학번을 사용할 수 있습니다. 실제 회원 계정은 운영자가 별도로 준비합니다.

## 비용 제한

- 변환당 AI 요청 1회, 출력 최대 1,024토큰, 다른 모델로 자동 전환 없음
- 회원별 분당 2회·하루 20회·월 50회, 사이트 전체 월 1,000회·동시 20건
- 20건 초과 요청은 순서대로 대기; 화면에 대기 순서를 표시하고 빈자리가 생기면 자동 시작
- 대기 확인은 5초 간격이며 AI 호출 없음; 대기·변환 중 화면을 열어 두세요
- 동일 요청 ID는 24시간 이내 저장된 결과를 재사용
- 제한은 PostgreSQL에서 원자적으로 적용; 실패한 시도도 사용 횟수에 포함
- 실제 Muse 시도 전에 보수적으로 4원씩 누적 예약하고 20,000원에서 자동 중지; 실패·월 변경·회원 삭제로 초기화하지 않음

누적 금액은 공식 단가를 기준으로 여유를 둔 앱 내부 계산입니다. 현재 Meta 화면의 $0.50과 토큰 단가 계산 $0.0003699가 불일치하며 실제 청구액은 미확정입니다. 실제 카드 청구액·다른 앱 호출·호스팅 비용까지 제한하지 않습니다. [계산과 적용 범위](docs/AI_BUDGET.md)를 확인하세요.

Contributor는 입력과 응답을 Meta의 모델 학습에 사용하는 조건이 있습니다. 변환 화면에 안내하며, 승인된 일반 회원은 로그인 시 동의 체크박스가 기본 선택됩니다. 회원이 체크를 해제하면 실제 모델을 호출하지 않습니다. [Meta 조건·요금](https://dev.meta.ai/docs/pricing-rate-limits), [Vercel 모델](https://vercel.com/ai-gateway/models/muse-spark-1.3-contributor).

## 로컬 실행

```bash
make install
make dev
```

<http://127.0.0.1:8080>에서 확인합니다. 기본 실행은 회원 로그인 화면부터 표시하며 `.env.local`의 Supabase 설정을 읽습니다. 승인된 회원만 변환 화면을 볼 수 있습니다. `make dev`는 모의 모델이며 실제 회원 변환은 서버 키를 설정한 뒤 `make dev-ai`로 실행합니다. 로그인 없이 화면만 보는 개발 실행은 `make dev-mock`입니다. LOCAL_TEST 문서를 따르세요.

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
