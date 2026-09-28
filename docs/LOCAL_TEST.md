# 로컬 실행과 GPT 연결

현재 코드는 OpenAI GPT-5.4 mini 전용입니다. 모델·추론 `none`·출력 1,024토큰 제한은 `backend/app/openai_policy.py`에서 고정합니다.

## 회원 화면 개발

```bash
make install
make dev
```

<http://127.0.0.1:8080>에서 로그인 화면을 확인합니다. `make dev`는 `.env.local`의 Supabase 설정과 개발용 모의 모델을 사용하며 유료 AI를 호출하지 않습니다. 승인된 회원만 변환 화면에 접근합니다.

## 실제 회원 변환

1. Supabase에 회원·대기열·기존 예산 마이그레이션을 적용한 뒤 `202609280004_openai_budget.sql`을 적용합니다. [설정 절차](VERCEL_SUPABASE_SETUP.md)를 따릅니다.
2. Git 제외 `.env.local`에 `.env.local.example`의 Supabase 공개/서버 키와 `OPENAI_API_KEY`를 설정합니다. 현재 새 OpenAI 키의 모델 메타데이터 접근은 확인했으며 운영 DB 예산 업그레이드도 적용했습니다.
3. `make preflight-openai`로 키·모델 접근과 DB 예산 정책을 조회합니다. 유료 생성을 수행하지 않습니다.
4. 기존 서버를 종료하고 `make dev-ai`를 실행한 뒤 승인된 계정으로 로그인합니다.
5. 전략을 변환하면 GPT 유료 요청이 발생합니다. 회원 경로에는 [누적 2만 원 예산](AI_BUDGET.md)이 적용됩니다.

서버는 `OPENAI_API_KEY`만 읽고 `https://api.openai.com/v1/chat/completions`로 요청합니다. Meta·Gateway 연결과 키 별칭은 제거했습니다. 키는 Git·채팅·로그에 남기지 않습니다. 환경파일 수정 후 서버를 재시작해야 새 값이 적용됩니다.

일반 회원은 키 입력이나 설정 화면 없이 서버 공용 키를 사용합니다. 운영자는 설정에서 연결 여부·회원 승인·누적 예산을 확인합니다. 연결 표시와 읽기 전용 모델 조회는 실제 생성 성공을 보장하지 않습니다.

## 로그인 없는 개발 모드

`make dev-mock`은 로컬 모의 실행입니다. 설정 창에 OpenAI 키를 연결하면 해당 서버 메모리에서만 실제 GPT를 사용할 수 있으며 연결 해제·서버 재시작으로 지워집니다. 이 모드는 회원 DB와 누적 예산을 사용하지 않습니다. loopback·Host·Origin·요청 헤더를 확인하고 운영/Vercel에서는 차단합니다.

## 검증과 배포

```bash
make test
make lint
make test-frontend
make test-sql
.venv/bin/python scripts/evaluate.py
```

마지막 명령은 오프라인 모의 평가입니다. 유료 평가에는 별도 `--live` 옵션이 필요합니다. [평가 안내](../evals/README.md)를 확인하세요.

[OpenAI 배포 절차](OPENAI_DEPLOYMENT.md)에 따라 Vercel에 새 코드를 배포해야 운영에 적용됩니다. 로컬 키가 자동으로 운영에 복사되지는 않습니다. FASTEXPR·BRAIN 설정 생성 성공과 수익성·BRAIN Simulate 성공은 별도입니다.
