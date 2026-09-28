# 배포 후 변환 실패 복구 작업

> 이 문서는 이전 시점의 조사·결정 기록입니다. 현재 코드는 GPT 전용이며 Meta 연결과 Contributor 동의 코드는 제거했습니다. 현재 모델·설정은 [OPENAI_DEPLOYMENT.md](OPENAI_DEPLOYMENT.md)를 확인하세요.

## 현재 확인한 사실

2026-09-28 10:03 KST 기준 운영 배포는 `a9eb21c`입니다. 로컬과 운영 서버에서 사용하는
Meta 키의 SHA-256 비교 ID가 같습니다. 양쪽 `/v1/models` 요청이 HTTP 200을
반환하므로 키가 빠지거나 서로 다른 키를 선택한 상황이라는 증거는 없습니다.
로컬에는 `muse-spark-1.3-contributor`가 있지만 운영 서버의 진단에서는 없습니다.
승인받은 운영 변환 1회는 `404 / model_not_found`로 실패했습니다.

이는 키 변수 오류 가능성을 낮추지만, 서버 IP·지역·모델 레지스트리·런타임 중
어느 차이가 원인인지 확정하지는 않습니다. 지역 제한이나 Meta 장애라고
단정하지 않습니다. [Meta 모델 조회 문서](https://dev.meta.ai/docs/models).

## 배포한 추가 진단

이번 변경은 관리자 전용 조회를 보완합니다. 변환 요청 내용, 모델, 키,
자동 재시도 정책과 예산 설정은 바꾸지 않습니다.

- `/api/admin/provider-check`: 모델 목록 GET 1회, 공개된 모델 ID만 표시.
- `/api/admin/provider-check?details=true`: 위 조회와 Contributor 개별 모델 GET
  1회. 총 GET 2회이며 AI 생성 POST는 없습니다.
- 실제 선택한 키 변수 이름과 기존 키 비교 ID를 표시합니다. 키 원문은
  반환하지 않습니다.
- Python·httpx 버전, 함수 지역, 배포 커밋, 공급자 코드 SHA-256,
  프록시 변수 설정 여부를 비교합니다. 프록시 주소와 환경 변수 원문은
  반환하지 않습니다.
- 승인된 관리자만 조회할 수 있고 변환 횟수·예산을 예약하지 않습니다.

로컬의 실제 Meta 키로 모델 목록과 Contributor 개별 모델을 조회했으며,
두 요청 모두 HTTP 200입니다. 목록 8개에 Contributor가 포함되고,
선택된 변수는 `META_API_KEY`, 프록시 설정은 없습니다. 이 검사는 AI를
생성하지 않았습니다.

운영자 승인 후 진단 코드 `a9eb21c`를 Production에 배포했습니다.
Vercel 배포는 [Ready 상태](https://vercel.com/ksj12/natural-language-brain-alpha-harness/DbXEikcF1N9iNwGi52DdMAjxf2qJ)이며 운영 도메인에 적용됐습니다.
최초 상세 조회는 로그인 세션이 만료되어 401로 끝났고 Meta를 호출하지
않았습니다. 홈페이지에서 정상 세션 갱신 후 상세 조회 1회가 완료됐습니다.

| 항목 | 로컬 | Production |
| --- | --- | --- |
| 선택된 키 변수 | META_API_KEY | META_API_KEY |
| 키 비교 ID | 동일 | 동일 |
| 공급자 코드 SHA-256 | 동일 | 동일 |
| httpx | 0.28.1 | 0.28.1 |
| 프록시 설정 | 없음 | 없음 |
| Python | 3.14.3 | 3.12.14 |
| 함수 지역 | 로컬 | icn1 (서울) |
| 모델 목록 GET | 200, 8개 | 200, 4개 |
| 1.2 Contributor | 있음 | 있음 |
| 1.3 Contributor | 있음 | 없음 |
| 1.3 개별 모델 GET | 200 | 404 / model_not_found |

서버에서 반환된 공개 모델 ID는 `muse-image-1.0`, `muse-spark-1.1`,
`muse-spark-1.2`, `muse-spark-1.2-contributor`입니다. Contributor 전체가
불가능한 상황이 아니라 1.3을 포함한 새 모델들이 서버 목록에 없는 상황입니다.
키 변수·코드 불일치·환경 프록시라는 설명과는 맞지 않습니다.

### 다음 비교: 함수 실행 지역 변경, 별도 배포 승인 필요

`vercel.json`의 단일 함수 지역을 `icn1`에서 Vercel 기본 지역인
미국 워싱턴 D.C. `iad1`로 바꾸는 변경을 준비했습니다.
서버 위치에 따른 Meta 모델 접근 차이가 있는지 확인하려는 비교 실험이며,
지역 제한이나 해결 성공이 확정됐다는 뜻은 아닙니다.
[Vercel 지역 설정 문서](https://vercel.com/docs/functions/configuring-functions/region).

승인 후 배포하고 동일 상세 정보 조회 GET 2회만 실행합니다. 키·모델·
공급자 코드·호출 횟수·출력 상한·예산은 그대로입니다. 새 API 키와
AI 생성 호출이 필요하지 않습니다. 한국의 사용자 및 Supabase와 함수
사이 거리가 늘어나 로그인·DB 요청 지연이 늘 수 있습니다. 이 비교가
실패하면 추측으로 여러 지역을 반복 배포하지 않고 아래 연결 대안을 보고합니다.
실제 변환이 필요하면 새로 1회 승인을 받습니다.

## 기존 연결로 해결되지 않을 때의 대안

새 키 발급, 충전, 키 저장, 운영 연결 변경은 아직 하지 않았습니다.
다른 서비스의 키를 Meta에 보내거나 Meta 키를 다른 서비스에 보내지 않습니다.

| 연결 | 같은 Contributor 모델 | 공식 입력 / 출력 단가, 100만 토큰당 | 준비 상태 |
| --- | --- | --- | --- |
| Meta 직접 | 예 | $0.10 / $0.20 | 현재 사용, 서버 접근 차이 조사 중 |
| Vercel AI Gateway | 예 | $0.10 / $0.20 | 기존 연결 코드 있음, 새 전용 키·잔액 확인과 요청 파라미터 검증 필요 |
| OpenRouter | 예 | $0.10 / $0.20 | 모델 목록과 Meta 제공 경로 확인, 전용 키와 연결 코드 추가 필요 |

공식 가격 및 모델 정보:
[Meta](https://dev.meta.ai/docs/pricing-rate-limits),
[Vercel AI Gateway](https://vercel.com/ai-gateway/models/muse-spark-1.3-contributor),
[OpenRouter](https://openrouter.ai/meta/muse-spark-1.3-contributor).

모델 목록에 있는 것만으로 새 계정의 실제 생성 성공을 보장할 수 없습니다.
Gateway의 무료 크레딧이 이 모델에 적용된다고 가정하지 않습니다.
OpenRouter의 최소 크레딧 구매 금액은 $5이며 결제 수수료는 별도입니다.
이는 사용 단가와 다른 초기 충전 금액입니다.
[OpenRouter 약관](https://openrouter.ai/terms/).

비용을 최소화하려면 같은 Contributor 모델을 고정하고, 변환 1회당
AI 요청 1회, 오류 자동 재시도 0회, 검색·도구 호출 0회, 출력 상한 1,024
토큰을 유지합니다. 비싼 Standard 모델로 자동 변경하지 않습니다.
다른 연결을 추가할 경우에도 승인·사용량·예산 검사를 우회하면 안 됩니다.

현재 Meta 대시보드의 3회 사용 $0.50 표시는 공식 토큰 단가로 계산한 값과
차이가 있으며 아직 청구 상세로 해명되지 않았습니다. 새 연결의 단가가
같다는 이유만으로 실제 청구도 같거나 기존 표시가 오류라고 단정하지 않습니다.
앱의 추정 비용과 결제 서비스의 실제 청구는 따로 확인해야 합니다.

## 검증

추가 진단 및 비밀값 차단·관리자 권한 검사를 포함한 로컬 전체 테스트:
`310 passed, 30 skipped`. `make lint` 통과. PostgreSQL 통합 검사는
별도 CI에서 실행하며, 이번 로컬 결과의 30개 생략 항목은 통과로 세지 않습니다.

진단 코드의 [GitHub CI](https://github.com/blockcoder-sj/natural-language-brain-alpha-harness/actions/runs/36364382738)에서 backend(임시 PostgreSQL 포함), frontend, gateway가 모두 통과했습니다.
지역 변경은 아직 배포하지 않았습니다. 현재 변환 실패가 해결됐다고
판단하려면 운영 연결이 정상이고 새로 승인한 실제 변환 1회가 성공해야 합니다.


## 부록: 기존 배포 설정 문서의 진단 기록

## 배포 후 Meta 404 진단 (2026-09-28)

Chrome에서 Production `c5f45cd`의 Ready 상태와 실제 `/api/convert` 요청 2건의
Meta `POST /v1/chat/completions` 404를 확인했습니다. Supabase 인증·승인·한도 조회는
정상이며, 연결 방식은 `meta`, 고정 모델은 `meta/muse-spark-1.3-contributor`입니다.
같은 날 로컬에 저장된 키의 `GET /v1/models`는 200으로 Contributor 모델을 반환했습니다.
이 모델 목록 조회는 전략이나 프롬프트를 보내지 않으며 AI 생성을 하지 않습니다.
당시에는 서버 키 일치 여부와 서버 모델 접근 여부가 미확정이었으며, 아래 후속 진단으로 키 일치와 서버 목록의 Contributor 누락을 확인했습니다.

진단 코드를 배포한 뒤 운영자로 로그인한 Chrome에서
`/api/admin/provider-check`를 열어 **배포 서버의** Meta 모델 목록을 확인할 수 있습니다.
이 경로는 승인된 관리자만 접근할 수 있고, 키·원문 오류·다른 모델 목록을 반환하지 않습니다.
변환 횟수·예산을 예약하지 않으며 자동 재시도나 실제 AI 생성도 하지 않습니다.
`httpStatus=200`과 `modelAvailable=true`면 해당 서버 키의 모델 목록에 Contributor가 포함됨을 확인합니다. 실제 생성 성공은 별도 검증이 필요합니다.
실제 변환 로그에는 HTTP 상태·허용 목록에 포함된 공급자 오류 코드·응답 종류만 남깁니다.
일반 404와 명시적 `model_not_found`를 구분하며 비밀키·전략·원문 오류는 기록하지 않습니다.

2026-09-28 09:30 KST 운영자 세션의 진단 요청이 배포 서버까지 도달했고, Vercel 로그에서 Meta `GET /v1/models` 200과 진단 경로 200을 확인했습니다. Chrome은 응답 화면을 `ERR_BLOCKED_BY_CLIENT`로 표시해 `modelAvailable` 값은 읽지 못했습니다. 따라서 키의 모델 목록 조회 인증·네트워크 연결은 확인했지만 Contributor 생성 권한이나 실제 생성 성공은 아직 확인한 것이 아닙니다. 미인증 별도 GET은 401로 차단됐습니다.

진단 버전 `896e2be`는 로컬 Python 테스트 297개 통과·SQL 관련 30개 건너뜀, 린트 통과를 확인했습니다. 해당 GitHub CI는 backend(PostgreSQL 포함)·frontend·gateway 모두 통과했습니다. 이번 변경은 DB 마이그레이션을 요구하지 않습니다. 진단 코드 배포와 승인받은 실제 AI 1회 검증은 완료했으며 실패 원인과 다음 비교는 아래에 기록합니다.

### 승인받은 실제 변환 1회 결과와 다음 비교

2026-09-28 09:34:59 KST 운영자 승인 후 단순 당일 수익률 역순위 전략으로
실제 변환을 **1회만** 실행했습니다. 요청 ID는 `ccxwp-1790555699362-6bc5524baa8d`이며,
배포 `dpl_AYRrKht34VAoGC5YUdmQ8BLpuqyw`의 로그에서 Supabase 인증·승인·변환 예약·
예산 예약·결과 저장은 200, Meta 생성 요청은 404를 확인했습니다.
안전한 오류 로그는
`code=model_access http_status=404 upstream_code=model_not_found response_shape=json_error`
입니다. 자동 재시도나 다른 모델 호출은 없었습니다.

모델 ID `muse-spark-1.3-contributor`는 공식 문서와 일치합니다.
Meta는 이 오류를 모델 ID 또는 팀의 모델 접근 문제로 안내하지만, 이 로그만으로
키 불일치나 지역 제한을 단정할 수 없습니다. [Meta 오류 안내](https://dev.meta.ai/docs/error-handling).

후속 진단 변경은 Chrome의 JSON 화면 차단 때문에 응답을 읽지 못한 문제를 줄이기 위해
같은 `/api/admin/provider-check`에 HTML 표시를 추가합니다. 브라우저에서 열면 HTML,
API 클라이언트에서는 JSON을 반환하며 관리자 승인 확인·캐시 금지·CSP·프레임 차단은 유지합니다.
`keyFingerprint`는 저장된 API 키 SHA-256의 앞 16자리로, 로컬과 서버가 같은 키를 쓰는지
비교하기 위한 값입니다. 키 원문은 반환하거나 로그에 남기지 않습니다.
모델 목록 조회만 수행하므로 실제 AI 생성·변환 횟수·예산 예약이 없습니다.
새 변경은 테스트 299개 통과·SQL 관련 30개 건너뜀·린트 통과했으며,
GitHub CI의 backend(PostgreSQL 포함)·frontend·gateway도 모두 통과했습니다.
2026-09-28 09:46 KST 운영자 재배포 승인 후 `2ed26fa`를 Production에 배포했습니다.
배포 ID는 `dpl_5txMpR7RhucAqMCyuN28RxVwHuWt`이며 Ready와 기본 도메인 적용을 확인했습니다.
관리자 HTML 진단 화면에서 다음 값을 읽었습니다.

```json
{
  "apiProvider": "meta",
  "model": "muse-spark-1.3-contributor",
  "inferencePerformed": false,
  "status": "failed",
  "httpStatus": 200,
  "modelAvailable": false,
  "errorCode": "model_access",
  "keyFingerprint": "aa0ecc064a45a9ec"
}
```

직후 로컬에서 같은 키로 `GET /v1/models`를 다시 조회한 결과 200이며
`muse-spark-1.3-contributor`가 포함됐습니다. 키 비교 ID도 동일하고 로컬 HTTP 프록시는
설정되지 않았습니다. 이번 후속 진단은 서버 1회·로컬 1회 모델 목록 조회만 했고
실제 AI 생성은 추가로 실행하지 않았습니다. Chrome에서 진단 결과가 보이지 않던 문제는
해결됐으나 변환 실패는 아직 남아 있습니다.

동일한 키·모델 주소에서 요청 환경에 따라 Meta의 모델 목록이 달라지는 현상까지
확인했습니다. Meta의 지역/IP 판정 또는 카탈로그 라우팅 차이는 가능성이며 원인으로
확정하지 않았습니다. 지역 설정·키·모델·제공자를 임의 변경하지 않았습니다.
Meta 상태 화면은 `Status information is unavailable`을 표시했으므로 전체 서비스 장애도
확정하지 않았습니다. [지원 문의 초안](META_SERVER_MODEL_ACCESS_REPORT.md)은 문서로만
준비했으며 Meta에 전송하지 않았습니다.
추가 실제 AI 요청은 새로운 승인 없이 실행하지 않습니다.
