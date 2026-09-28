# Meta 6회 호출 비용 표시 조사와 모델 대안

> 이 문서는 이전 시점의 조사·결정 기록입니다. 현재 코드는 GPT 전용이며 Meta 연결과 Contributor 동의 코드는 제거했습니다. 현재 모델·설정은 [OPENAI_DEPLOYMENT.md](OPENAI_DEPLOYMENT.md)를 확인하세요.

확인일: 2026-09-28. 계정 화면 조회, 기존 저장 기록, 공식 문서, 로컬 비용 함수 계산을 대조했습니다. 이번 조사에서 새 AI 추론 요청은 0회입니다.

## 현재 판정

**공식 Contributor 단가와 Usage의 달러 표시가 일치하지 않는 것은 확인했습니다. 실제로 1.06달러가 결제됐다는 증거는 현재 없습니다.** 원화 환산 숫자를 달러로 표시하는 문제를 가장 유력하게 보고 있으나, 응답의 금액 단위·통화가 공개되지 않아 그 구현 원인과 실제 청구 예정액은 아직 확정하지 못했습니다.

추가로 Meta가 현재 배포한 공개 JavaScript를 읽어 **Spend의 표시 통화가 USD로 고정돼 있다는 구현은 확인했습니다.** 서버 비용의 원래 통화와 실제 청구 예정액은 공급자 답변 또는 청구서와 대조해야 확정할 수 있습니다. 문의 초안은 [Meta 과금 문의](../artifacts/membership-proof/meta-billing-inquiry.md)에 준비했습니다. **문의는 아직 전송하지 않았습니다.**

## 공개 포털 코드에서 추가로 확인한 사실

현재 사용량 페이지가 실제로 로드한 공개 번들을 다운로드해 실행 없이 읽었습니다. 일반 문서 추측이 아닌 현재 표시 구현입니다.

1. `usageMetricValue`는 숫자형 `USAGE_BILLABLE_COST`를 `1e8`로 나눕니다.
2. 값에 `formatted_amount`가 있으면 숫자·마이너스·소수점을 제외한 문자를 제거합니다. 이 경로에서 원래 통화 기호를 보존하지 않습니다.
3. `formatCompactCurrency`는 금액 앞에 고정된 `$`를 붙입니다. 이 함수는 결제 통화나 환율을 인자로 받지 않습니다.
4. Spend 그래프의 범례도 문자열 `USD`로 고정돼 있습니다.
5. 서버의 일별 수치에 이 변환을 적용해 더한 뒤 Spend로 표시합니다. 표시 경로에서 KRW→USD 환율 변환은 수행하지 않습니다.

이로써 **화면에 USD가 보인다는 사실만으로 서버 비용이 실제 USD라는 것을 증명할 수 없다는 점**은 확정했습니다. 다만 서버가 이미 USD로 환산해 값을 주는지, KRW로 주는지는 이 클라이언트 코드만으로 확정하지 못했습니다. 원본 사용량 조회 주소를 브라우저로 읽으려는 시도는 `ERR_BLOCKED_BY_CLIENT`로 차단됐으며, 인증 정보를 추출하거나 다른 경로로 우회하지 않았습니다.

원문: [사용량 변환·금액 포매터 번들](https://dev.meta.ai/_next/static/chunks/0fdf_mqmq1t5q.js), [Spend 화면 번들](https://dev.meta.ai/_next/static/chunks/00zf9fj7en94j.js). 수집 URL·SHA-256·발견 문자열은 [증빙 JSON](../artifacts/membership-proof/meta-public-billing-code.json)에 보관했습니다.

## 계정 화면에서 확인한 사실

조회 범위: 9월 22–28일, 전체 API 키. Contributor 필터를 적용해도 총계가 같았고 모델 선택 목록에는 Contributor 하나만 있었습니다.

| 항목 | 관측 값 |
| --- | --- |
| 모델 | muse-spark-1.3-contributor |
| 요청 | 6회 |
| 입력 토큰 | 약 5k (UI 반올림 값) |
| 출력 토큰 | 약 1.4k (UI 반올림 값) |
| Spend | $1.06, 범례 USD |
| 검색·도구·이미지·음성·분할 | 모두 0 |
| Billing 결제 통화 | Korean Won (KRW) |
| Billing 현재 잔액 | ₩0, 현재 납부할 금액 없음 |
| Payment activity | 거래 내역 없음 |

같은 계정의 Models 화면에서도 Contributor 입력 $0.10, 출력 $0.20 단가를 표시했습니다. [Usage](https://dev.meta.ai/usage), [Billing](https://dev.meta.ai/billing), [Models](https://dev.meta.ai/platform/models)는 로그인 후 계정별 화면입니다.

Usage는 집계가 제한적으로 제공되며 불일치는 크레딧 조정으로 처리한다는 안내도 표시합니다. 이는 이 계정의 오류가 이미 인정됐다는 뜻은 아닙니다. 결제 내역이 비어 있다는 사실도 앞으로 비용이 청구되지 않는다는 보장은 아닙니다. 결제는 임계금액 또는 월 청구일에 일어나며 영수증은 Payment activity에서 확인합니다. [Meta 청구 안내](https://dev.meta.ai/help/billing/api-bill), [결제 내역 안내](https://dev.meta.ai/help/billing/unrecognized-payment).

## USD 결제와 키 교체에 관한 추가 확인

같은 날 현재 계정의 `Billing → Business information → Edit`를 열었습니다. 편집 화면에는 이름과 주소만 있었고, 국가·통화 선택 항목은 없었습니다. 입력이나 저장 없이 닫았습니다. 이 계정의 해당 화면에서 USD로 변경할 수 없다는 관측이며, 다른 절차나 공급자 지원을 통한 변경 가능성까지 부정하는 것은 아닙니다. 공식 [사업자 정보 수정 안내](https://dev.meta.ai/help/teams-and-members/update-business-info)와 [결제 설정 안내](https://dev.meta.ai/help/billing/set-up-billing)도 통화 변경 방법은 설명하지 않습니다.

Contributor 단가는 모델과 토큰 사용량으로 정해집니다. 같은 팀에서 키만 재발급해도 공개된 모델 단가는 바뀌지 않습니다. 실제 청구 통화를 USD로 바꿀 수 있다면 KRW 청구 설정과 USD 표시의 불일치는 제거할 수 있지만, 현재 서버 금액의 통화가 미확인 상태라 과금 문제가 해결된다고 확정할 수 없습니다. 다른 결제 팀으로 옮기는 경우에는 그 팀에서 발급한 키가 필요하며, 단순히 현재 팀의 키를 재발급하는 것과는 다릅니다. [공식 단가](https://dev.meta.ai/docs/pricing-rate-limits), [인증 안내](https://dev.meta.ai/docs/authentication).

## Billing 잔액과 Usage의 반영 시점 상세 확인

2026-09-28 오후 같은 팀의 화면을 다시 읽었습니다. 요청 6회, 입력 약 5k, 출력 약 1.4k, Spend $1.06, Billing 잔액 ₩0, 결제 내역 없음은 유지됐습니다. 추가 유료 추론 호출은 하지 않았습니다.

- Billing의 `Billing data timing` 버튼에 연결된 DOM 안내는 `Billing data may be delayed up to an hour`입니다. 현재 공개 [Billing 번들](https://dev.meta.ai/_next/static/chunks/0uq48gpor__m0.js)에도 동일한 문구가 있습니다. SHA-256: `a9256e2b997750eb14ed1d3125b51e5e1547aa1dca128c938bdf209c186800d4`.
- Usage의 같은 안내도 최대 1시간 지연을 명시합니다. 따라서 사용 직후 서로 다른 집계 시점의 값이 보일 수 있습니다. 이것이 이 계정의 잔액이 0인 원인이라고 확정한 것은 아닙니다.
- `About Spend` 안내는 `The approximate amount of money you've spent.`입니다. Usage 금액은 공급자가 근사값으로 설명하는 지표이며 결제 완료 내역이 아닙니다.
- 입력·출력 토큰 안내는 추론 응답에서 측정한 토큰 수를 해당 사용 요금 계산에 사용한다고 설명합니다.
- Payment activity는 거래가 생기면 기록이 표시된다고 안내합니다. 반면 Current balance는 결제 전 누적 잔액에 해당합니다. 공식 청구 안내도 비용은 사용 시 누적되고, 임계금액 또는 매월 1일에 결제한다고 설명합니다. 결제 전에는 원래 금액을 표시하지 않는 구조라고 해석할 근거는 없습니다.
- 그래프의 9월 27일 입력 사용량도 확인했습니다. 전날 사용량이 이미 포함돼 있어 최근 사용분의 1시간 지연만으로 전체 불일치를 설명했다고 판단하지 않았습니다.
- 현재 계정의 잔액이 왜 ₩0인지, 반올림·크레딧·서버 갱신 상태 중 무엇이 적용됐는지는 확인되지 않았습니다. 특정 원인을 추측해 확정하지 않았습니다.

확인한 DOM 문구와 공개 번들의 증빙은 [추가 관측 기록](../artifacts/membership-proof/meta-billing-ui-observations.json)에 저장했습니다. 서버 비용의 통화·단위와 실제 청구 원장 금액을 대조해야 최종 원인을 확정할 수 있습니다. [공식 청구 안내](https://dev.meta.ai/help/billing/api-bill), [결제 내역 안내](https://dev.meta.ai/help/billing/unrecognized-payment).

## Contributor 학습 조건과 앱의 동의 검사

현재 로컬 코드는 `muse-spark-1.3-contributor`로 고정돼 있습니다. 계정에서 앞서 모델 필터를 적용한 6회 내역도 Contributor였습니다. 학습 활용 허용이 할인 조건이며, 특정 요청이 실제로 학습 데이터에 채택됐다고까지 확인한 것은 아닙니다. [공식 가격](https://dev.meta.ai/docs/pricing-rate-limits), [Meta 약관 6.1](https://dev.meta.ai/legal/terms-of-service).

`backend/app/conversion.py:119`는 Muse 요청의 `trainingConsent`가 false이면 AI 호출 전에 HTTP 400으로 차단합니다. `backend/app/static/js/membership.js:192`는 승인된 일반 회원에게 체크박스를 자동으로 체크합니다. 사용자가 체크를 해제하면 차단되므로, 동의 플래그는 필수이지만 매번 사용자가 직접 체크하는 구조는 아닙니다. 기존 `test_training_acknowledgement_is_required_before_ai_or_quota`를 프로젝트 가상환경에서 실행해 통과했으며, 동의가 없는 요청에서 AI 호출과 예산 예약이 모두 0인 것을 확인했습니다. 코드는 변경하지 않았습니다.

## 수치 대조

공식 요금은 **100만 입력 토큰당 $0.10, 100만 출력 토큰당 $0.20**입니다. 정액 호출료나 최소 선납금은 가격 안내에 명시되지 않았습니다. [Meta 공식 요금](https://dev.meta.ai/docs/pricing-rate-limits).

현재 화면의 반올림 토큰 수를 사용하면:

```text
입력: 5,000 × $0.10 / 1,000,000 = $0.00050
출력: 1,400 × $0.20 / 1,000,000 = $0.00028
합계:                                  $0.00078
```

6회 전체의 추정치입니다. $1.06은 이 계산보다 약 1,359배 큽니다. 정확한 6회 합계 토큰은 현재 UI만으로 알 수 없어 이 값은 근사치입니다.

이전 3회 저장 기록은 입력 2,501·출력 599·캐시 입력 0, Spend $0.50, 포털 조회 응답의 `usage_billable_cost=50221578`입니다. 당시 원본 응답에는 통화·단위 필드가 없었습니다. 공식 토큰 요금은 정확히 $0.0003699입니다.

```text
포털 원본 금액을 100,000,000으로 나누면: 0.50221578
이를 공식 달러 계산값으로 나누면:      1357.706893755...
이 배율을 현재 6회 계산값에 적용하면:   0.00078 × 1357.706893755 = 1.059011...
소수 둘째 자리 표시:                   1.06
```

이전 3회에서 얻은 배율이 현재 6회 표시값도 재현합니다. KRW 결제 통화와 함께 볼 때 **원화 숫자에 USD 기호가 붙었다는 가설에 강한 근거**입니다. 현재 포털 코드가 1e8로 나누는 것은 확인했지만, 서버 비용의 원래 통화와 1357.7069라는 배율이 실제 공급자 환율인지는 확정하지 못했습니다. 다른 서버 단위 변환·청구 집계 결함도 공급자 확인 전에는 배제하지 않습니다.

## 코드 또는 다른 사용량이 원인인지

- `backend/app/model_policy.py`의 추론 수준은 `minimal`, 출력 최대치는 1,024입니다. 요청과 환경변수가 이를 높이는 경로가 없습니다.
- `backend/app/provider.py`는 변환당 POST 1회를 수행하며 자동 재시도·다른 모델 전환·검색 도구를 요청하지 않습니다.
- 비용 함수의 올림 단위는 **micro-USD (100만분의 1달러)**입니다. 달러 단위로 올리지 않습니다. 로컬 실행에서 817입력/160출력은 114 micro-USD = $0.000114, 5,000입력/1,400출력은 780 micro-USD = $0.00078이었습니다.
- 앱의 비용 추정과 4원 예산 예약은 내부 계산입니다. Meta 요청에는 청구 금액을 보내지 않으므로 이 계산이 포털의 Spend를 정하지 않습니다.
- 고가 Standard 모델로 계산해도 같은 토큰 수는 $0.0122입니다. 모델 등급 차이만으로 $1.06이 설명되지 않습니다.
- 시스템 지침·JSON 스키마가 입력을 늘리지만 포털 입력 토큰 집계와 공식 요금을 곱한 값 자체가 매우 작습니다.
- 다른 키의 사용이 포함될 수 있어 전체 키 및 모델 필터로 확인했습니다. 보이는 계정 총량은 여전히 6회이며 검색 등 별도 과금 사용량은 0입니다.

위 코드 검증은 현재 로컬 파일에 관한 것입니다. 실제 6회는 계정의 모델·토큰·요청 총량을 기준으로 판단했습니다. 과거 배포본이 현재 로컬 리팩터링과 같다고 가정하지 않았습니다.

## 대안 비교

각 호출이 입력 1,000·청구 출력 200토큰을 사용한다고 가정한 **1,000회 합계**입니다. 동기식 일반 요금, 캐시 할인·검색·세금 제외입니다. 모델마다 토크나이저와 실제 출력량이 달라 실사용 비용은 바뀝니다.

| 모델·조건 | 입력 $/100만 | 출력 $/100만 | 1,000회 예상 비용 |
| --- | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 0.10 | 0.20 | $0.14 |
| Qwen3.7 Flash, Global 지역, 입력 ≤32k | 0.028 | 0.11 | **$0.05** |
| Qwen3.7 Flash, Singapore, 입력 ≤32k | 0.03 | 0.13 | **$0.056** |
| GPT-6 Luna, Standard, 짧은 입력 | 0.10 | 0.50 | $0.20 |
| Gemini 3.5 Flash-Lite, 무료 범위 | 무료 | 무료 | **$0** |
| Gemini 3.5 Flash-Lite, 유료 Standard | 0.30 | 2.50 | $0.80 |

Qwen 요금은 일시 할인 제외 일반 요금이며 Global에는 Tokyo 등 지역이 있습니다. 구조화 출력도 지원합니다. 짧은 입력에서 현재 Muse 대비 표의 기준으로 약 64% 저렴합니다. 실제 계정에서 선택한 배포 지역·키·모델 가용성을 확인해야 합니다. [Qwen3.7 Flash 공식 모델·지역별 가격](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash).

Qwen3.7 Flash는 기본적으로 사고 모드가 켜져 있어 `enable_thinking=false`를 명시해야 불필요한 추론 출력을 피할 수 있습니다. OpenAI 호환 API를 제공하지만 기존 Muse의 `reasoning_effort=minimal`을 그대로 복사하면 안 됩니다. JSON 응답 형식과 현재 스키마의 실제 호환성 검증도 필요합니다. [사고 모드 설정](https://www.alibabacloud.com/help/en/model-studio/deep-thinking), [호환 API](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions), [구조화 출력 안내](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output).

GPT-6 Luna는 구조화 출력과 `reasoning.effort=none`을 지원합니다. Standard 출력 요금 때문에 이 작업에서 Muse보다 저렴하지 않습니다. Batch/Flex의 절반 가격을 일반 동기식 가격으로 취급하지 않았습니다. [OpenAI 요금](https://developers.openai.com/api/docs/pricing), [Luna 모델·추론 설정](https://developers.openai.com/api/docs/models/gpt-6-luna).

Gemini 3.5 Flash-Lite는 공식 무료 입력·출력 범위가 있어 소규모 실습 비용을 0으로 만들 후보입니다. 무료 데이터는 제품 개선에 사용되며 실제 RPM/RPD 등 한도는 계정의 AI Studio에서 확인해야 합니다. 유료 전환 시 Muse보다 단가가 높습니다. [Google 가격](https://ai.google.dev/gemini-api/docs/pricing), [무료 범위와 한도](https://ai.google.dev/gemini-api/docs/rate-limits).

과거 저가 모델 안내는 현재 가용성과 다를 수 있습니다. Gemini 2.5는 공식 API 문서상 기존 이용자 위주로 접근을 제한해 새 프로젝트 후보에서 제외했습니다. Groq의 저가 Llama 3.1 8B는 무료·개발자 플랜에서 2026-08-16 종료됐습니다. GPT-5 nano 스냅샷도 2026-12-11 종료가 공지돼 새 전환 우선안에서 제외했습니다. [Google 현재 가용성](https://ai.google.dev/gemini-api/docs/deprecations), [Groq 종료 안내](https://console.groq.com/docs/deprecations), [OpenAI 종료 안내](https://developers.openai.com/api/docs/deprecations).

DeepSeek Flash의 현재 캐시 미적중 요금은 비혼잡 시간 입력 $0.15·출력 $0.60, 혼잡 시간 $0.30·$1.20입니다. 동일 기준 $0.27–$0.54/1,000회라 기본 대안으로는 더 비쌉니다. 캐시 적중의 매우 낮은 입력 가격만 보고 전체 비용이 저렴하다고 판단하지 않았습니다. [DeepSeek 공식 요금](https://api-docs.deepseek.com/quick_start/pricing/).

## 권장 방향과 남은 확인

유료 단가를 낮추려면 Qwen3.7 Flash의 사고 모드를 끈 구성이 우선 검증 후보입니다. 무료 실습을 우선하면 Gemini 3.5 Flash-Lite의 실제 무료 한도부터 확인하는 것이 적합합니다. 두 모델의 한국어 전략 해석 정확도는 아직 측정하지 않았습니다.

현재 가격 불일치는 모델 선택 문제와 별개로 해결해야 합니다. 공급자 문의는 정확한 6회 토큰 수, 적용 SKU·단가, 최소 요금·반올림, 세금·수수료, 금액 응답 단위·통화, 실제 청구 예정액, 표시 오류 또는 과금 오류 및 크레딧 여부를 수치로 대조하도록 준비했습니다.

키만 교체하면 현재 Muse 전용 모델 제한과 요청 형식 때문에 작동하지 않습니다. 전환 시 공급자 어댑터·모델 ID·주소·추론 옵션·단가·데이터 사용 동의 문구를 함께 수정하고 대표 전략과 지원 밖 전략을 검증해야 합니다. 이번 조사에서는 모델·키·배포 설정을 변경하지 않았습니다.
