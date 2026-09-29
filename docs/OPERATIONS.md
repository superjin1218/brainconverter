# 운영 기준

운영 구성은 Vercel FastAPI·Supabase Auth/DB·OpenAI GPT-5.4 mini입니다. GPT 전환과 가설 변환 기능은 배포됐습니다. 키와 배포는 [OPENAI_DEPLOYMENT.md](OPENAI_DEPLOYMENT.md), 기존 회원 DB 설정은 [VERCEL_SUPABASE_SETUP.md](VERCEL_SUPABASE_SETUP.md), 변경별 검증은 [CODE_REVIEW.md](CODE_REVIEW.md)를 따릅니다.

## 모델과 비용

모델·추론 수준·출력/요청 상한·단가는 `openai_policy.py`에서 관리합니다. OpenAI 추론은 `none`, 출력은 최대 1,024토큰, 요청은 1회이며 재시도나 대체 모델 호출은 없습니다. 키 연결·상태 조회는 실제 생성 성공을 뜻하지 않습니다.

GPT-5.4 mini의 100만 토큰당 일반 입력 $0.75·캐시 입력 $0.075·출력 $4.50을 적용하며 항목별 micro-USD 단위로 올림합니다. OpenAI는 시도당 34원을 내부 누적 예산에 예약합니다. 실제 공급자 청구액과 예약액은 다르며 [계산과 적용 범위](OPENAI_DEPLOYMENT.md#비용-정책)를 확인하세요. Meta 과금 조사 기록은 [META_BILLING_INVESTIGATION.md](META_BILLING_INVESTIGATION.md)에 남아 있습니다.

## 회원과 예산

가입·이메일 인증 이후에도 운영자 승인까지 pending입니다. 승인된 운영자는 설정 화면에서 회원 승인·이용 중지·누적 예산을 조회합니다. 누적 20,000원 예약 제한과 월/회원 쿼터는 Supabase DB가 관리합니다. 외부 공급자의 실제 카드 청구액 제한과 동일하지 않습니다.

대기·실행 중인 요청의 ID를 유지하며 중복 확인으로 새 유료 호출을 만들지 않습니다. 결과 보관이 실패하면 화면의 경고를 확인하고 생성 코드를 바로 복사합니다.

## 연결 진단

승인된 운영자만 `/api/admin/provider-check`를 조회합니다. 선택 모델 메타데이터만 GET으로 읽고 AI 변환·예산 예약을 실행하지 않습니다. 결과의 `providerSourceSha256`은 호출·정책·연결·오류·진단 모듈을 묶은 SHA-256입니다. 키 비교 ID와 공개 모델 식별자만 반환합니다.

`modelAvailable`은 선택 모델 메타데이터 접근 여부입니다. 실제 생성 성공과 잔액 충분 여부는 별도 확인이 필요합니다.

## 변경 검증

`make test`, `make lint`, `make test-frontend`로 오프라인 검증합니다. SQL 변경 시 `make test-sql`로 외부 Supabase 대신 임시 PostgreSQL을 검증합니다. `scripts/evaluate.py`의 기본 실행은 오프라인이며, OpenAI `--live --limit 1` 실행은 비용이 발생합니다.

키 입력 후 `make deploy-openai`로 배포하며, 저장한 코드·환경변수는 배포 시점부터 운영에 적용됩니다. 이전 Cloudflare·Cloud Run 운영 경로는 제거했습니다.
