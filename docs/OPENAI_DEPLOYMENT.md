# OpenAI 키 입력 후 배포

2026-09-28 사용자가 배포 명령을 실행한 뒤 운영 홈페이지와 `/api/health` HTTP 200, OpenAI GPT-5.4 mini, 준비한 공급자 소스 해시 일치를 확인했습니다. 추론 수준은 `none`이며 실제 유료 전략 생성은 별도 테스트 대상입니다.

## 키 입력

프로젝트 루트의 Git 제외 파일 `.env.local`에 새 키를 입력합니다. 기존 Supabase 값은 유지합니다.

```dotenv
HARNESS_PROVIDER=openai
OPENAI_MODEL=gpt-5.4-mini
OPENAI_API_KEY=
MODEL_TIMEOUT_SECONDS=35
```

키를 채팅·커밋·공개 화면에 붙여 넣지 않습니다. 로컬의 기존 Meta 키 변수와 연결 구현을 삭제했습니다. OpenAI 키가 없거나 오류가 나면 호출을 중단합니다.

모델과 추론 수준은 `backend/app/openai_policy.py`의 `OPENAI_MODEL`, `OpenAIModelPolicy.reasoning_effort`에 있고, 같은 파일의 `payload()`가 실제 요청에 넣습니다. `.env.local`의 `OPENAI_MODEL`은 이 고정값과 일치해야 하며 다른 모델이면 호출 전에 중단합니다.

GPT-5.5 mini는 공식 API 모델·가격을 확인하지 못해 기본값으로 쓰지 않았습니다. GPT-5.4 mini의 공식 지원 최저 추론 값인 `none`을 [openai_policy.py](../backend/app/openai_policy.py)에서 고정합니다. 사용자 입력이나 환경변수로 추론·출력 상한을 올릴 수 없습니다. [OpenAI 공식 모델 문서](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

## 최초 배포에 필요한 연결

키만으로 Vercel 계정 인증이나 Supabase 스키마 변경 권한이 생기지는 않습니다. 이 PC의 CLI 로그인 프로세스는 인증 완료를 보고했습니다. 아래 절차는 다른 컴퓨터나 인증이 만료된 경우에 필요합니다. Node.js 22 이상을 사용하세요.

1. Vercel CLI에 로그인합니다. 기존 `ksj12/natural-language-brain-alpha-harness` 프로젝트로 연결합니다.

   ```sh
   npx --yes vercel@60.1.3 login
   ```

2. 운영 DB에는 2026-09-28 16:01:38 KST에 005까지 적용했습니다. 이전 예약액 86원·14건을 보존하고 새 집계 0원을 확인했습니다. [005 마이그레이션](../supabase/migrations/202609280005_gpt_usage_reset.sql)은 사용자가 요청한 **최초 1회 비용·관리자 사용횟수 초기화**와 GPT 토큰 비용 영구 집계를 추가합니다. 과거 작업·예약 기록은 보존합니다. Supabase SQL Editor에서 적용하거나, 자동 적용에 필요한 Management API 토큰 `SUPABASE_ACCESS_TOKEN`을 Git 제외 `.env.local` 또는 프로세스 환경에 설정합니다. 토큰은 Vercel로 전송하지 않습니다. 신규 DB는 모든 마이그레이션을 파일명 순서대로 적용합니다.

배포 스크립트는 다른 Supabase URL이나 다른 Vercel 연결 파일을 발견하면 중단합니다. 배포 시 등록하는 OpenAI 키·Supabase 서버 키의 목적지는 기존 Vercel 프로젝트의 **Production Secret**입니다.

## 실행

이 컴퓨터에서는 Finder에서 [deploy-openai.command](../scripts/deploy-openai.command)를 더블클릭하면 프로젝트 위치와 설치된 Node.js 22를 선택한 뒤 배포 명령을 실행합니다. 키·Supabase 설정은 기존 Git 제외 `.env.local`에서 읽습니다. 현재 CLI 인증은 완료됐지만 Codex의 Vercel 브라우저 접근은 저장된 사이트 차단 설정에 막혀 있습니다. 실행 파일은 사용자가 직접 배포할 때 사용합니다.


```sh
make preflight-openai  # 조회만 수행: 키·선택 모델 접근, DB 예산 정책
make deploy-openai    # 검증 → 필요 시 DB 업그레이드 → 운영 변수 등록 → 배포 → 확인
```

`make deploy-openai`는 Python 검사·테스트와 프런트엔드 테스트를 실행합니다. Docker가 실행 중이고 PostgreSQL 테스트 이미지가 있으면 `RUN_SQL_TESTS=1 make deploy-openai`로 SQL 테스트도 포함할 수 있습니다. 인증·DB 준비가 부족하면 원인을 출력하고 배포를 중단합니다. 키는 명령행 인자나 출력에 포함하지 않고 CLI의 표준 입력으로 전달합니다. 배포 파일에서 환경파일·테스트·개발 스크립트를 제외합니다.

배포 확인은 운영 주소 `/api/health`의 공급자·모델·실제 공급자 소스 해시를 대조합니다. 관리자 `/api/admin/provider-check`는 OpenAI의 선택 모델을 GET으로 조회하며 유료 생성을 실행하지 않습니다. 실제 전략 해석 품질·잔액 충분 여부·생성 성공은 이 조회만으로 보장하지 않습니다. 사이트의 유료 변환 요청은 사용자가 직접 실행해야 확인할 수 있습니다.

## 비용 정책

일반 입력 $0.75, 캐시 입력 $0.075, 출력 $4.50 / 100만 토큰을 응답 `usage`로 계산합니다. 각 항목을 **마이크로달러** 단위로 올림합니다. 예: 입력 1,000 + 출력 200토큰은 캐시가 없으면 **$0.001650**입니다. 실제 인보이스 금액은 공급자 내역으로 확인합니다.

한 번의 생성·자동 재시도 없음·최대 출력 1,024토큰·직렬화 요청 16,000바이트·35초 상한을 유지합니다. 요청 저장 옵션은 `store=false`, 서비스 등급은 `default`로 설정합니다. Contributor 동의 UI·요청 필드·서버 검사를 제거했습니다.

DB는 OpenAI 시도마다 **34원**을 내부 누적 예산에서 보수적으로 예약합니다. 이는 실제 호출 가격이 아니라 최악 입력·출력 및 2,000원/USD를 기준으로 만든 내부 한도입니다. 과거 예약 기록은 그대로 유지하고, 사용자가 요청한 005 최초 적용 시점부터 예산을 새로 집계합니다. 실패·회원 삭제·월 변경으로 환불하거나 초기화하지 않으며, 누적 20,000원 한도를 넘기기 전에 중단합니다. 이 앱 밖의 키 사용·세금·실제 공급자 청구 총액은 이 한도에 포함되지 않습니다.

환경변수 등록 이후 배포가 실패하면 기존 배포는 계속 운영되며 새 환경변수는 이후 배포에 사용됩니다. 실패한 단계부터 원인을 해결한 뒤 같은 명령을 다시 실행할 수 있습니다. 이미 적용한 DB 마이그레이션을 다시 실행해도 누적액을 초기화하지 않습니다.
