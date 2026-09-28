# 개발 원칙

## 모듈 경계

- `openai_policy.py`: OpenAI의 고정 모델·추론·입출력 상한·단가를 관리합니다.
- `provider_config.py`: 서버 환경에서 OpenAI 키·타임아웃을 읽습니다.
- `chat_provider.py`: 단일 HTTP 생성 요청과 응답·오류 처리를 공유합니다.
- `openai_provider.py`: OpenAI의 모델 검사·캐시 비용·읽기 전용 진단을 담당합니다.
- `provider.py`: 공급자 조립과 공통 상태 조회를 담당합니다.
- `response_schema.py`: 모델에 전달할 구조화 출력 스키마를 생성합니다.
- `provider_types.py`: 공급자 인터페이스와 토큰/비용 결과 형식을 정의합니다.
- `mock_provider.py`: 오프라인 개발·회귀 검증만 담당하며 운영에서는 선택을 차단합니다.
- `conversion.py`: 회원 작업 예약·대기·예산·저장과 변환 흐름을 조정합니다.
- `service.py`: 단일 모델 해석, 원문 검사, 컴파일 순서를 조정합니다.
- `compiler.py`: Strategy IR을 FASTEXPR로 바꾸는 순수 함수를 둡니다.
- `settings.py`: BRAIN 설정 기본값과 명시값을 해석합니다.
- `membership.py`: Supabase 로그인·세션·회원 승인·DB 호출을 담당합니다.
- `security.py`: 요청 크기를 제한합니다.
- `main.py`: 애플리케이션을 조립하고 HTTP route와 응답 헤더를 정의합니다.
- 프런트엔드는 API, 폼, 회원 상태, 키 설정, 결과 렌더링, WebMCP를 분리합니다.

## 변경 규칙

1. 새 기능은 소유할 모듈이 명확할 때만 추가합니다.
2. route나 UI 이벤트 안에 비즈니스 로직을 직접 작성하지 않습니다.
3. 동일 규칙을 복사하지 않고 하나의 함수 또는 객체로 관리합니다.
4. 사용하지 않는 함수·상수·의존성은 같은 변경에서 삭제합니다.
5. 모델 정책은 OpenAI 불변 정책 객체에서 관리합니다. 환경변수·요청 데이터로 추론 수준이나 출력 상한을 노출하지 않습니다.
6. 외부 모델 출력은 Pydantic schema를 통과시킵니다.
7. 버그 수정에는 재현 테스트를 추가합니다.
8. API 키, 전략 원문, BRAIN 자격증명을 로그에 남기지 않습니다.
9. 테스트는 mock transport를 사용합니다. 유료 호출 결과와 오프라인 검증을 구분합니다.

## 완료 조건

```bash
make test
make lint
make test-frontend
make test-sql  # SQL 변경 시 Docker의 임시 PostgreSQL로 검증
.venv/bin/python scripts/evaluate.py  # 오프라인 회귀 전략
```

변경 범위의 검사가 통과해야 합니다. 현재 운영은 Vercel·Supabase이며 이전 Cloudflare·Cloud Run 구현은 Git 이력으로만 남깁니다.
