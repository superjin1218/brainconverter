# 자연어 → WorldQuant BRAIN 코드 웹사이트

Ubuntu 자체 서버 운영(3000번 포트, 기존 Cloudflare Tunnel, 이메일 인증 없는 공개 가입·관리자 승인)은 [Ubuntu 운영 절차](docs/UBUNTU_OPERATIONS.md)를 따릅니다. 인증 정책 변경과 배포 결과는 [인증 정책 배포 보고서](docs/PASSWORD_ONLY_DEPLOYMENT_REPORT.md)에서 확인합니다. 아래 Vercel 관련 내용은 이전 운영 기록입니다.

자연어 전략을 FASTEXPR 초안과 BRAIN 설정 12개로 변환합니다. 웹사이트는 Vercel, 회원가입·승인·사용량 DB는 Supabase를 사용합니다. 별도 Google Cloud·Oracle·Cloudflare 서버가 필요하지 않습니다.

운영 사이트: [BRAIN Alpha Harness](https://natural-language-brain-alpha-harness.vercel.app) · 저장소: [blockcoder-sj/natural-language-brain-alpha-Converter](https://github.com/blockcoder-sj/natural-language-brain-alpha-Converter). 저장소 이름과 로컬 폴더·Vercel 프로젝트 이름은 다릅니다.

구체적인 지표·기간·전략 이름이 없어도 시작할 수 있습니다. **“덜 출렁이는 종목이 좋아”, “갑자기 사람들이 몰리는 주식이 궁금해”, “잘 오르면서 안정적인 주식이 좋아”**처럼 가설을 적으면 AI가 측정 방법과 빠진 조건을 정해 전략 초안을 만듭니다. AI가 고른 대리 지표·기간·조합은 가정으로 표시합니다.

새 운영 변환은 `IntentIR(intent-v3)`을 사용합니다. AI가 원문의 근거 문구, 측정 방법, 선호 방향(높은 값/낮은 값), 비교 집단을 정하고 서버가 점수식을 만듭니다. 이름이 정해진 전략 템플릿을 선택하는 구조가 아닙니다. 같은 근거로 신호를 중복 추가하거나 음수 가중치로 방향을 뒤집는 것을 막고, 합성 측정값을 바꿔 코드의 점수가 선언한 선호 방향으로 움직이는지 검사합니다. 설명도 같은 계획과 코드에서 생성합니다. 기존 `DraftIR`·`StrategyIR`은 이전 결과와 오프라인 회귀 호환용입니다.

**원하는 방향으로 다듬기**와 개선 실험도 같은 AI 응답에서 가설에 맞게 생성합니다. 선택지를 누르면 수정 전략과 기존 시뮬레이션 설정을 입력창에 반영하고, 다시 변환 버튼을 눌렀을 때만 새 AI 요청을 보냅니다. 코드의 계산 설명은 검증된 식에서 생성합니다. 변환당 AI 호출은 여전히 1회입니다. **다듬기 선택지에는 유사한 제안의 반복과 제목의 방향 반전이 확인되어 보완이 필요합니다.** 현재 코드 검사는 선택지의 제목·설명·수정 전략 사이의 의미 일치나 알파 개선 효과까지 보장하지 않습니다.

운영 모델은 **OpenAI GPT-5.4 mini**, 추론은 최저값 **none**으로 고정했습니다. 실제 호출은 OpenAI만 지원합니다. 변환 규칙을 담은 [SKILL.md](backend/app/skills/brain-strategy/SKILL.md)를 시스템 지침으로 읽어 **한 번** 해석합니다. Python이 구조·원문 조건을 검사하고 허용된 FASTEXPR를 생성합니다. 여러 에이전트의 합의나 자동 모델 재시도는 사용하지 않습니다.

## 먼저 볼 문서

- 다음 작업을 위한 현재 맥락: [SESSION_CONTEXT.md](docs/SESSION_CONTEXT.md)
- 새 OpenAI 키 입력·한 번에 배포: [OPENAI_DEPLOYMENT.md](docs/OPENAI_DEPLOYMENT.md)

- 로컬 실행·키 연결: [LOCAL_TEST.md](docs/LOCAL_TEST.md)
- Vercel·Supabase 회원 사이트 설정: [VERCEL_SUPABASE_SETUP.md](docs/VERCEL_SUPABASE_SETUP.md)
- 완료한 검증과 아직 남은 작업: [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
- 실제 가설 5건의 코드와 남은 문제: [HYPOTHESIS_VALIDATION_2026-09-29.md](docs/HYPOTHESIS_VALIDATION_2026-09-29.md)
- 모델 검증 범위·월 비용 (이전 조사 기록): [MODEL_COST_AND_VALIDATION.md](docs/MODEL_COST_AND_VALIDATION.md)
- 누적 2만 원 자동 중지: [AI_BUDGET.md](docs/AI_BUDGET.md)
- 이전 Meta 배포 실패 조사 기록: [DEPLOYED_CONVERSION_RECOVERY.md](docs/DEPLOYED_CONVERSION_RECOVERY.md)
- 푸시 전 코드 검토·검증 기록: [CODE_REVIEW.md](docs/CODE_REVIEW.md)

## 최근 반영과 검증 · 2026-09-29

- [PR #7](https://github.com/blockcoder-sj/natural-language-brain-alpha-Converter/pull/7): 조건식의 독립 검증으로 선언하지 않은 점수 항 추가를 차단하고, ‘주식·주가’를 주 단위 기간으로 오인하는 문제를 수정했습니다. 정적 보안 검토와 회귀 결과는 [코드 검토 기록](docs/CODE_REVIEW.md), 병합·배포 확인 결과는 PR 본문에 기록합니다.
- [PR #6](https://github.com/blockcoder-sj/natural-language-brain-alpha-Converter/pull/6): README·작업 맥락 정리 main 병합 완료.
- [PR #4](https://github.com/blockcoder-sj/natural-language-brain-alpha-Converter/pull/4): 원문 근거와 선호 방향 검사, 서버 점수식 생성 적용 완료.
- [PR #5](https://github.com/blockcoder-sj/natural-language-brain-alpha-Converter/pull/5): 상세 입력 예시 적용 및 main 병합·운영 배포 완료. 확인한 운영 코드 기준은 `756dbaf`입니다. 홈페이지·상태 API HTTP 200, 배포 소스 일치, 실제 화면의 빈 입력창 예시 표시를 확인했습니다.
- 최신 기능/화면 변경의 GitHub CI: Python·SQL 491개 + 프런트엔드 40개, 총 **531개 통과**. 별도 모의 전략 회귀는 105/105이며 실제 AI 정확도 수치가 아닙니다.
- 선호 방향 검사 배포 후 운영 UI에서 **실제 AI 5회(기존 오답 재검사 2회 + 다른 가설 3회)**를 실행했습니다. 모두 코드가 생성됐고 선택한 대리 지표의 기본 점수 방향은 가설과 부합했습니다. 다듬기 선택지 문제와 대리 지표의 한계는 [실제 검증 기록](docs/HYPOTHESIS_VALIDATION_2026-09-29.md)에 남겼습니다. 알파 개선안의 품질을 체계적으로 평가하거나 BRAIN 백테스트를 수행한 것은 아닙니다.

`git.deploymentEnabled=false`이므로 Git 푸시만으로 재배포되지 않습니다. 협업 변경은 별도 브랜치와 PR로 올리고, 승인된 변경을 main에 병합·배포합니다. 이전 Meta 연결·비용 기록은 이력 문서에 보존하며 현재 실제 생성 경로는 OpenAI뿐입니다.

## 입력 예시: 세 문장이 하나의 전략

빈 입력창에는 다음 상세 예시를 표시합니다. 실제 입력값은 비어 있으며 입력을 시작하면 예시가 사라집니다.

> 미국 TOP3000 주식의 최근 5일 누적 수익률(종가 기준)이 높을수록 높은 점수를 주세요.
>
> 거래량이 최근 20일 평균의 1.5배 이상일 때만 점수를 갱신하고, 그 외에는 이전 점수를 유지해 주세요.
>
> 산업 중립화(INDUSTRY), Delay 1, Decay 4, Truncation 0.08을 적용해 주세요.

위 세 문장은 **거래량 조건을 붙인 단기 모멘텀 전략 하나**입니다. 대상 종목군·측정 기간·선호 방향, 점수 갱신 조건과 미충족 시 처리, 시뮬레이션 설정을 차례로 명시한 작성 예시입니다. 성과가 검증된 추천 알파를 뜻하지 않습니다. 생략한 설정은 기본값으로 채웁니다.

## 회원 이용 흐름

누구나 **이메일·비밀번호로 회원가입 → 즉시 로그인 → 승인 대기 → 운영자 승인 → 전략 변환** 순서로 이용합니다. 이메일 소유 확인과 가입 인증메일 발송은 사용하지 않으며 Resend·Custom SMTP가 필요하지 않습니다. 가입 직후에는 DB의 `private.brain_members`에 `pending/member`로 등록됩니다. 가입 폼·사용자 메타데이터로 역할이나 승인 상태를 지정할 수 없습니다.

HTML·JavaScript·FastAPI는 비밀번호 **6~256자**를 요구합니다. 영문·숫자·특수문자 조합 제한은 없으며 6자 이상 숫자만으로도 가입할 수 있습니다. Supabase의 비밀번호 인증 자체는 유지합니다.

Supabase 설정은 **Allow new users to sign up ON, Confirm email OFF, Minimum password length 6, 문자 조합 요구 없음, Custom SMTP OFF**로 맞춥니다. 기존 DB에는 [새 인증 정책 SQL](supabase/migrations/202610310001_password_only_membership.sql)만 추가 적용합니다. 과거 초기화 마이그레이션을 다시 실행하지 않습니다. Confirm email이 켜진 상태에서는 앱이 가입 요청을 중단하므로 인증메일이 발송되지 않습니다.

운영자는 **설정 → 회원 승인 관리**에서 승인·거절·이용 중지를 처리합니다. **이메일과 이름은 가입자가 입력한 정보이므로 사칭할 수 있습니다.** 자동으로 표시되는 이메일 인증 상태도 소유 증명이 아닙니다. 승인 전에 기존 연락처 등 별도 경로로 본인을 확인하세요. 관리자 권한은 `approved/admin`, 변환 권한은 `approved`로 검사하며 이메일 주소·메타데이터를 근거로 자동 승인하지 않습니다. 첫 관리자 설정도 독립적으로 확인한 사용자 UUID를 명시해야 합니다. 기존 관리자와 회원의 상태는 변경하지 않습니다.

인증 토큰은 HttpOnly·Secure·SameSite=Lax 쿠키에 보관합니다. 서버는 Supabase에서 로그인 신원을 확인하고 DB의 승인 상태를 검사합니다. 일반 회원에게 설정 버튼·키 입력창·남은 횟수 표시는 숨기며 서버 공용 키를 사용합니다. 모델 키와 Supabase 서버 키는 Git에서 제외된 `.env.local`에 보관합니다. Ubuntu 운영·재배포 절차는 [운영 문서](docs/UBUNTU_OPERATIONS.md)를 참고하세요.

## 비용 제한

- 변환당 AI 요청 1회, 출력 최대 1,024토큰, 다른 모델로 자동 전환 없음
- 회원별 분당 2회·하루 20회·월 50회, 사이트 전체 월 1,000회·동시 20건
- 20건 초과 요청은 순서대로 대기; 화면에 대기 순서를 표시하고 빈자리가 생기면 자동 시작
- 대기 확인은 5초 간격이며 AI 호출 없음; 대기·변환 중 화면을 열어 두세요
- 동일 요청 ID는 24시간 이내 저장된 결과를 재사용
- 제한은 PostgreSQL에서 원자적으로 적용; 실패한 시도도 사용 횟수에 포함
- OpenAI 시도 전에 보수적으로 34원씩 누적 예약하고 20,000원에서 자동 중지; 실패·월 변경·회원 삭제로 초기화하지 않음

누적 금액은 앱 내부의 보수적 예약액입니다. 실제 공급자 청구서·다른 앱 호출·호스팅 비용까지 제한하지 않습니다. [새 비용 정책](docs/OPENAI_DEPLOYMENT.md#비용-정책)을 확인하세요.

Meta·Vercel AI Gateway 연결 코드와 Contributor 동의 화면·필드를 제거했습니다. OpenAI 키가 없으면 실제 변환이 중단됩니다. 과거 비용 조사와 DB 예약 원장은 보존합니다. 사용자 요청에 따른 GPT 집계 초기화는 [AI_BUDGET.md](docs/AI_BUDGET.md)에 설명합니다.

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

사용 가능한 데이터는 시가·고가·저가·종가·거래량·일간 수익률입니다. AI는 원자료·기간 수익률·변화량·평균·표준편차·평균 대비 비율·당일 두 데이터의 비율/차이·일중 가격 위치·상관관계 중 측정 방법을 고릅니다. 최대 3개 기준의 선호 방향을 적용한 순위와 양수 가중치를 조합하며 업종 내 비교와 조건부 점수를 지원합니다. 임의의 점수식 전체를 생성하는 대신 이 측정 방법들을 조합해 가설을 표현합니다. 일별 누적 가격 수익률은 `close / ts_delay(close, n) - 1`로 계산합니다.

입력한 조건을 우선하고 생략된 조건만 AI가 초안으로 정합니다. 원문 근거·동종업계 비교·명시된 숫자·일부 데이터·수익률 기간·거래량 비교 조건과 계획에서 코드로 옮긴 선호 방향을 검사합니다. 합성값 검사는 선언한 측정값을 바꿨을 때의 점수 순서를 확인하며 실제 시장 데이터나 BRAIN 실행 검사가 아닙니다. AI가 원문에 맞는 측정 방법과 선호 방향을 골랐는지까지 완전히 증명하지는 않습니다. 가정과 코드 설명을 확인해 수정할 수 있습니다. 재무·뉴스 데이터, 보유·손절·익절 주문 실행은 지원하지 않습니다. `trade_when`은 조건이 참일 때 점수를 갱신하고 거짓이면 직전 값을 유지합니다.

고정 응답을 사용하는 자동 테스트는 컴파일·검증·화면 동작을 확인하며 실제 AI의 해석 정확도를 나타내지 않습니다. `evals/semantic_composition_cases.json`에는 실제 호출용 사례를 별도로 보존합니다. 유료 검증은 `scripts/evaluate.py --live --cases evals/semantic_composition_cases.json --limit 3`처럼 명시적으로 실행하며, 괄호나 동치인 곱셈 순서 차이는 허용합니다.

PASS는 내부 변환 검사 통과입니다. 전략의 수익성이나 BRAIN 실행 성공을 뜻하지 않습니다. BRAIN 로그인·Simulate·Alpha 제출은 자동 실행하지 않습니다. 생성 결과와 설정을 BRAIN에 옮겨 직접 실행해야 합니다.

기본 설정: FASTEXPR / EQUITY / USA / TOP3000 / Delay 1 / Neutralization SUBINDUSTRY / Decay 4 / Truncation 0.08 / Pasteurization ON / Unit Handling VERIFY / NaN Handling OFF / Test Period 0 years·0 months. 명시한 설정을 우선하고 빠진 값만 기본값으로 채웁니다.

2026-09-28 유지보수 정리에서 이전 Cloudflare·Cloud Run 코드와 배포 파일을 제거했습니다. 현재 모듈 구조는 [ARCHITECTURE.md](docs/ARCHITECTURE.md), 개발 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 따릅니다. 추론 수준은 [openai_policy.py](backend/app/openai_policy.py)의 `OPENAI_POLICY.reasoning_effort`에서 `none`로 고정합니다.
