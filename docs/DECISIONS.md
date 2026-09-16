# 확정된 제품 결정

## 기능

- 자연어 전략은 6개 semantic agent가 독립적으로 Strategy IR로 해석합니다.
- 필드별 다수결과 0.5 이상의 합의 신뢰도를 요구합니다.
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
- 모델 비용 예상은 월 약 `$3.51`, 전체 hard limit은 `$10`으로 시작합니다.
- Cloud Run은 scale-to-zero, 최대 인스턴스 2로 제한합니다.
- 브라우저는 AI 공급자 API를 직접 호출하지 않습니다.
- BRAIN 자동 로그인·시뮬레이션·제출은 범위에서 제외합니다.

