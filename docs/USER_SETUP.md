# 사용자가 직접 설정할 항목

소스 코드와 배포 설정이 준비된 뒤 아래 항목만 계정 소유자가 직접 구성합니다.

## 1. OpenAI API

- OpenAI Platform에서 API 키를 발급합니다.
- Cloud Run Secret에 `OPENAI_API_KEY`로 등록합니다.
- GitHub 파일, 브라우저, Cloudflare Pages 환경변수에는 키를 넣지 않습니다.
- 월 사용 한도를 먼저 설정합니다. 월 1,000회 기준 권장 hard limit은 `$10`입니다.

## 2. Google Cloud

- 결제 계정이 연결된 프로젝트를 선택합니다.
- Cloud Run, Artifact Registry API를 활성화합니다.
- 선택한 리전에 `brain-alpha` 이름의 Docker Artifact Registry 저장소를 한 번 생성합니다.
- 배포 서비스 계정과 GitHub Workload Identity Federation을 연결합니다.
- GitHub 저장소 Variables에 `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_SERVICE`를 등록합니다.
- GitHub 저장소 Secrets에 `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`를 등록합니다.
- Cloud Run Secret에 `OPENAI_API_KEY`, `GATEWAY_SHARED_SECRET`을 등록합니다.

## 3. Cloudflare

- Worker용 KV namespace를 만들고 `QUOTA` binding에 연결합니다.
- Worker Secret에 `BACKEND_URL`, `GATEWAY_SHARED_SECRET`을 등록합니다.
- GitHub Secrets에 `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`를 등록합니다.
- Cloudflare Access에서 허용할 학교 이메일 또는 이메일 목록을 설정합니다.
- 필요하면 사용자 도메인을 Worker route에 연결합니다.

## 4. 첫 운영 전 확인

- `/api/health`가 `ok`를 반환하는지 확인합니다.
- 허용되지 않은 이메일이 차단되는지 확인합니다.
- 한 사용자가 일일 제한을 넘으면 429가 반환되는지 확인합니다.
- 자연어 전략 한 건으로 FASTEXPR와 12개 설정이 모두 출력되는지 확인합니다.
- Cloud Run 로그에 전략 원문이나 API 키가 남지 않는지 확인합니다.
