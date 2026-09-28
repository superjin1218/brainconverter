# Meta 서버 모델 접근 차이 진단

> 이 문서는 이전 시점의 조사·결정 기록입니다. 현재 코드는 GPT 전용이며 Meta 연결과 Contributor 동의 코드는 제거했습니다. 현재 모델·설정은 [OPENAI_DEPLOYMENT.md](OPENAI_DEPLOYMENT.md)를 확인하세요.

2026-09-28 기준. 실제 변환 실패는 아직 해결되지 않았습니다.
아래 문의 초안은 Meta에 전송하지 않았습니다. 운영자가 검토 후
[Meta 지원](https://dev.meta.ai/support)에 접수할 수 있습니다.
키 원문·비밀번호·회원 정보·전략 입력은 첨부하지 않습니다.

## 확인된 결과

| 항목 | 로컬 macOS | Vercel Production |
| --- | --- | --- |
| API 제공자 | Meta 직접 API | Meta 직접 API |
| 서버에 저장된 키 | SHA-256 비교 ID 동일 | SHA-256 비교 ID 동일 |
| 모델 목록 주소 | `GET https://api.meta.ai/v1/models` | 동일 |
| 목록 HTTP 상태 | 200 | 200 |
| `muse-spark-1.3-contributor` 목록 포함 | 포함 | 미포함 |
| 최근 실제 생성 | 이전 3건 성공 확인 | 승인받은 1회는 404 `model_not_found` |

Vercel 함수 지역은 Seoul `icn1`입니다. 브라우저 로그인, Supabase 승인 확인,
변환 한도·예산 예약과 결과 저장은 정상 응답했습니다. 승인받은 생성 요청에는
자동 재시도나 다른 모델 호출이 없었습니다. 후속 키·목록 비교에는 실제 AI 생성을
하지 않았습니다. 모델 목록 차이의 내부 원인이나 국가/IP 판정은 아직 확정하지 못했습니다.

## 지원 문의 초안

**Subject:** Same Meta API key lists Contributor locally but omits it from Vercel Seoul; completion returns model_not_found

We are integrating `muse-spark-1.3-contributor` through the direct Meta API in a
server-side web application. The same stored API key, verified by matching a
SHA-256 comparison ID without exposing the credential, returns different model
catalogs depending on the request environment.

- From local macOS, `GET https://api.meta.ai/v1/models` returns HTTP 200 and includes
  `muse-spark-1.3-contributor`. This was checked again on 2026-09-28, shortly after
  00:46 UTC. No local HTTP proxy is configured.
- From Vercel Production in Seoul (`icn1`), the same authenticated GET returns
  HTTP 200 but does not include `muse-spark-1.3-contributor`.
- One approved request to `POST https://api.meta.ai/v1/chat/completions` from
  Vercel failed at approximately **2026-09-28 00:35:00 UTC** with HTTP **404**, code
  **`model_not_found`**. The request model was exactly `muse-spark-1.3-contributor`.
  We did not retry or switch models.
- Previous local calls to that Contributor model succeeded. Authentication to
  the catalog works from both environments.

Please investigate why this key's Contributor model availability differs for
Vercel Seoul server requests and whether the model catalog, request-origin
classification, or team access configuration needs correction. Please confirm
the supported deployment conditions for this integration. We would like to
keep using the Contributor model and avoid further billable test requests.

We can provide the team/project context securely in the support form. No API key
or end-user data is included in this report.

## 검증 기록과 다음 순서

진단 배포: `2ed26fa`, `dpl_5txMpR7RhucAqMCyuN28RxVwHuWt`.
실패한 앱 요청 ID: `ccxwp-1790555699362-6bc5524baa8d`.
이 값은 앱/Vercel 요청 식별자이며 Meta 응답의 요청 ID가 아닙니다.

Meta의 모델 접근 차이를 해소한 후 관리자 진단에서 `modelAvailable=true`를
확인하고, 별도 운영자 승인을 받아 실제 변환 1회를 검증합니다.
카탈로그 조회 성공만으로 실제 변환 성공이라고 판단하지 않습니다.
키 재발급·유료 모델 자동 전환·지역 우회·브라우저에 키 전달은 해결책으로 적용하지 않았습니다.

참고: [모델 목록](https://dev.meta.ai/docs/models),
[오류 코드](https://dev.meta.ai/docs/error-handling),
[지원 접수 안내](https://dev.meta.ai/help/support/contact-support).
