> 2026-09-27: 아래는 이전 Cloud Run·Cloudflare 구성의 기록입니다. 현재 Vercel·Supabase 설정은 [VERCEL_SUPABASE_SETUP.md](VERCEL_SUPABASE_SETUP.md), 로컬 테스트는 [LOCAL_TEST.md](LOCAL_TEST.md)를 따릅니다.

# 키 연결과 배포

> **2026-09-26 안내:** 이 문서의 클라우드 배포 절차는 기존 Google Cloud + Cloudflare 구성입니다. 사용자가 선택한 다음 배포 목표는 **Vercel + Supabase**이며, 이전 작업은 아직 수행하지 않았습니다. 지금 로컬 검증은 [LOCAL_TEST.md](LOCAL_TEST.md)를 따르세요. [배포 방향 변경](DECISIONS.md)을 참고하세요.

2026-09-23 기준, 코드·로컬 검증은 준비돼 있습니다. 실제 외부 서비스는 아직 배포하지 않았습니다. OpenAI 키 값은 모두 비어 있으며, 아래 계정 설정은 계정 소유자가 연결해야 합니다.

## 1. 로컬 미리보기

```bash
make install
make dev
```

`http://localhost:8080`에서 Mock 모드로 확인합니다. 외부 AI를 호출하지 않습니다. Python 3.11 이상, Gateway 작업에는 Node.js 22 이상이 필요합니다.

실제 API를 로컬에서 테스트하려면 화면의 **OpenAI API 키 연결**을 사용하세요. [로컬 테스트 안내](LOCAL_TEST.md)에 키 연결·변환·연결 해제 순서가 정리돼 있습니다.

## 2. 클라우드 계정값

```bash
cp .deploy.env.example .deploy.env
```

`.deploy.env`에 다음을 채웁니다. 이 파일은 Git에서 제외합니다.

| 이름 | 넣을 값 |
| --- | --- |
| GCP_PROJECT_ID | 결제가 연결된 Google Cloud 프로젝트 ID |
| GCP_REGION | 기본 `asia-northeast3` |
| GCP_SERVICE | 기본 `brain-alpha-harness` |
| CLOUDFLARE_ACCOUNT_ID | Worker를 소유할 계정 ID |
| ACCESS_TEAM_DOMAIN | `팀이름.cloudflareaccess.com` (https 없이) |
| ACCESS_AUD | 이 앱의 Cloudflare Access Application Audience 값 |
| ALLOWED_EMAILS | 초대한 회원 이메일을 쉼표로 구분 |
| ADMIN_EMAILS | 운영 현황을 볼 운영진 이메일; 회원 목록에도 포함 |

학교 전체 도메인을 허용하기보다 파일럿 운영진 3~5명의 정확한 이메일부터 넣으세요. Cloudflare Access의 애플리케이션 정책에도 동일한 회원을 허용합니다.

## 3. 계정 로그인과 리소스 준비

Google Cloud CLI를 설치한 뒤 실행합니다.

```bash
gcloud auth login
npm --prefix gateway ci
(cd gateway && npx wrangler login)
bash scripts/prepare-cloud.sh
```

준비 스크립트는 지정 프로젝트에 필수 API, Artifact Registry, 전용 Cloud Run 실행 계정, Secret Manager 항목을 만듭니다. 실행 계정에는 두 Secret의 읽기 권한만 부여합니다. Gateway 서명 키는 값이 없을 때 자동 생성하지만 출력하지 않습니다. **OpenAI 키는 생성하지 않습니다.**

호출 계정에는 서비스 활성화·서비스 계정·Secret 관리 권한이 있어야 합니다. Cloud Build의 빌드 계정에는 대상 Artifact Registry 쓰기와 빌드 저장소·로그에 필요한 권한이 있어야 합니다. 조직 정책에서 기본 빌드 계정 권한을 제한했다면 프로젝트 관리자에게 지정 빌드 계정 구성을 요청합니다.

## 4. OpenAI 키를 직접 추가

Google Cloud Console의 Secret Manager에서 `OPENAI_API_KEY`를 선택하고 **새 버전 추가**로 직접 붙여 넣습니다. 채팅·GitHub 파일·프런트엔드 설정에는 붙여 넣지 않습니다. `GATEWAY_SHARED_SECRET`은 준비 스크립트가 생성한 값을 사용합니다.

코드의 `.env.example`은 끝까지 빈 키 템플릿으로 남겨 둡니다. 모델은 비용 프로필이 고정된 `gpt-5-mini`입니다.

## 5. 배포

```bash
bash scripts/deploy.sh
```

스크립트가 테스트 후 컨테이너를 빌드하고 Cloud Run을 배포합니다. 최소 0·최대 2인스턴스, 65초 요청 제한, 인스턴스 동시성 2, 요청 기반 CPU를 적용합니다. Worker와 SQLite Durable Object를 배포한 뒤 계정값과 Gateway 서명 키를 Worker Secret에 등록합니다. OpenAI 키는 Cloud Run에만 전달합니다.

Worker가 출력한 호스트에 Cloudflare Access 애플리케이션을 연결합니다. `workers.dev` 호스트의 Access 보호를 사용하거나 소유 도메인을 Worker에 연결한 후 Access를 설정합니다. 설정 전에는 Worker가 JWT 없는 요청을 거부하므로 로그인 화면으로 진입하려면 Access 연결이 필요합니다.

별도 Pages 프로젝트는 필요하지 않습니다. 정적 화면도 같은 Worker 주소로 접속합니다.

## 6. GitHub Actions로 이후 갱신

| 종류 | 이름 |
| --- | --- |
| Variables | `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_SERVICE` |
| Secrets | `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` |

Google Cloud 배포 계정과 GitHub OIDC Workload Identity Federation을 연결해야 합니다. 이 구성은 준비 스크립트가 자동으로 만들지 않습니다. Cloudflare API 토큰은 해당 계정의 Worker 배포 권한만 부여합니다. 최초 리소스·Secret 설정 이후 `Deploy Cloud Run`과 `Deploy Cloudflare Gateway`를 수동 실행합니다.

## 7. 회원 초대 전 확인

- 회원은 로그인 가능하고 비회원·다른 AUD JWT·만료 JWT는 차단되는지 확인합니다.
- 자연어 전략 1건을 변환해 FASTEXPR·12개 설정·조건 대응표를 확인합니다.
- 같은 요청 ID를 다시 보내도 사용 횟수가 늘지 않는지 확인합니다.
- 분당·일일·월간 한도와 운영진 화면을 확인합니다.
- 실제 AI 평가와 BRAIN Simulate는 로컬 Mock 검증과 별도로 실행합니다.
- 우선 운영진 3~5명, `DAILY_LIMIT=10`으로 시작하고 성공률·p95·실비를 확인한 후 20명으로 확대합니다.

배포 상태는 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md), 운영 기준은 [OPERATIONS.md](OPERATIONS.md)에 기록합니다.
