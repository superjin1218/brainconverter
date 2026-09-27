# 확정된 제품 결정

## 2026-09-26 배포 방향 변경

- 사용자가 배포 플랫폼으로 **Vercel**, 회원 인증·데이터 관리용 백엔드로 **Supabase**를 선택했습니다. 오라클 VM이나 Google Cloud 서버를 별도로 운영하는 방향으로 진행하지 않습니다.
- 기존 Python/FastAPI 변환 API는 Vercel Functions에서 실행하고, Supabase Auth와 Postgres로 회원·사용량 관리를 옮기는 구성을 기준으로 준비합니다. Vercel은 FastAPI를 지원합니다: <https://vercel.com/docs/frameworks/backend/fastapi>.
- 이 선택은 **배포 목표**이며 아직 이전을 구현한 상태는 아닙니다. 기존 Cloudflare 인증·Durable Object 한도 관리와 Gateway HMAC 의존성을 교체하고 배포 진입점·실행시간을 설정해야 합니다. 이 문서 아래의 Cloud Run/Cloudflare 항목은 기존 구현을 기록한 것입니다.
- 현재 우선순위는 로컬 실제 API 검증입니다. 로컬 화면에서 입력한 키는 서버 메모리에서만 사용하고, 배포 시에는 운영자가 서버 Secret으로 설정합니다.

## 기능

- 자연어 전략은 6개 semantic agent가 독립적으로 Strategy IR로 해석합니다.
- 필드별 다수결과 각 필드에서 전체 6개 중 4개 이상 동의를 요구합니다.
- Python 컴파일러만 FASTEXPR을 생성합니다.
- 자연어에 설정이 빠져도 BRAIN 설정 12개를 항상 출력합니다.
- 명시 설정은 기본값보다 우선하며 값별 출처를 함께 표시합니다.
- 중립화는 BRAIN simulation setting에서 한 번만 적용해 이중 중립화를 막습니다.

## 기본 시뮬레이션 프로필

| 설정 | 값 |
| --- | --- |
| Language | FASTEXPR |
| Instrument Type | EQUITY |
| Region | USA |
| Universe | TOP3000 |
| Delay | 1 |
| Neutralization | SUBINDUSTRY |
| Decay | 4 |
| Truncation | 0.08 |
| Pasteurization | ON |
| Unit Handling | VERIFY |
| NaN Handling | OFF |
| Test Period | 0 years / 0 months |

## 운영

- 약 20명, 월 1,000회 사용을 기준으로 합니다.
- 모델 비용 `$3.51`은 초기 계획 가정입니다. Gateway가 모델 전용 월 `$10` 예산을 예약·정산하며 인프라 청구는 별도입니다.
- Cloud Run은 scale-to-zero, 최대 인스턴스 2로 제한합니다.
- 브라우저는 AI 공급자 API를 직접 호출하지 않습니다.
- BRAIN 자동 로그인·시뮬레이션·제출은 범위에서 제외합니다.


- 쿼터는 KV 대신 SQLite Durable Object 트랜잭션으로 관리합니다.
- 전체 2개를 넘는 요청은 대기열에 쌓지 않고 재시도 안내를 반환합니다.
- 정적 화면은 기존 Cloud Run 컨테이너에서 제공하고 Worker를 통해 접근합니다. Pages 배포를 추가하지 않아 운영 구성을 줄였습니다.
- 단일 extractor 실험 및 로컬 GPU 전환은 실제 모델 평가 후 검토합니다.

## 2026-09-27 — 운영 웹사이트와 단일 모델 해석

사용자 요청에 따라 웹사이트를 유지하고 Muse Spark 1.3 Contributor 한 번의 해석으로 전환합니다. SKILL.md 규칙과 Python 검사는 유지하며 다중 합의 호출은 제거합니다. Vercel·Supabase 가입/이메일 인증/운영자 승인을 사용하고 승인과 쿼터는 DB가 관리합니다. Contributor의 Meta 학습 활용은 변환 화면에서 동의를 요구합니다. 실제 배포와 유료 모델 확인은 아직 수행하지 않습니다.
