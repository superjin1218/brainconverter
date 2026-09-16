# 아키텍처

```text
회원 브라우저
  → Cloudflare Access
  → Cloudflare Worker Gateway
      - 회원 이메일 확인
      - 사용자별 일일 쿼터
      - Cloud Run 요청 HMAC 서명
  → FastAPI / FE-Harness
      - 6개 semantic agent 병렬 호출
      - Strategy IR 필드별 합의
      - source guard와 schema 검증
      - 결정론적 FASTEXPR 컴파일
      - 전체 시뮬레이션 설정 해석
  → 검증된 JSON 반환
```

## 신뢰 경계

브라우저는 모델 공급자와 직접 통신하지 않습니다. 모델 키는 Cloud Run Secret에만 있고 Gateway는 별도의 공유 비밀값으로 Cloud Run 요청을 서명합니다. Cloud Run은 운영 환경에서 유효한 Gateway 서명이 없는 변환 요청을 거부합니다.

## 데이터 정책

- 전략 원문과 완성 코드는 영구 저장하지 않습니다.
- 운영 로그에는 요청 ID, 사용자 해시, 상태 코드, 지연시간만 남깁니다.
- BRAIN 자격증명과 세션 정보는 입력받지 않습니다.
- 향후 학습 데이터 수집은 별도의 명시적 동의와 보관 기간을 도입한 뒤에만 추가합니다.

## 장애 정책

모델 호출은 40초 timeout, 1회 재시도, 최대 동시 하네스 작업 2개를 기본으로 합니다. 검증 단계가 하나라도 실패하면 임의 코드를 반환하지 않고 구조화된 오류를 반환합니다.

