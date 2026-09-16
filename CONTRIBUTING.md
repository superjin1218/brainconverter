# 개발 원칙

## 모듈 경계

- `provider.py`: 모델 공급자 호출과 응답 역직렬화만 담당합니다.
- `service.py`: agent 실행, 합의, 검증 순서를 조정합니다.
- `compiler.py`: Strategy IR을 FASTEXPR로 바꾸는 순수 함수만 둡니다.
- `settings.py`: BRAIN 설정 기본값과 명시값 해석만 담당합니다.
- `security.py`: Gateway 서명과 사용자 허용 여부만 검증합니다.
- `main.py`: 애플리케이션 조립과 HTTP route만 정의합니다.
- 프론트엔드는 API, 폼, 결과 렌더링, WebMCP를 서로 다른 모듈로 유지합니다.

## 변경 규칙

1. 새 기능은 소유할 모듈이 명확할 때만 추가합니다.
2. route나 UI 이벤트 안에 비즈니스 로직을 직접 작성하지 않습니다.
3. 동일 규칙을 두 위치에 복사하지 않고 하나의 함수 또는 객체로 승격합니다.
4. 사용하지 않는 함수·상수·의존성은 같은 변경에서 삭제합니다.
5. 기본 설정과 허용값은 한 곳에서 관리합니다.
6. 외부 모델 출력은 신뢰하지 않고 Pydantic schema를 통과시킵니다.
7. 버그 수정에는 재현 테스트를 먼저 추가합니다.
8. API 키, 전략 원문, BRAIN 자격증명을 로그에 남기지 않습니다.

## 완료 조건

```bash
pytest -q
ruff check backend
npm --prefix gateway run check
node --check backend/app/static/js/app.js
```

네 검사가 모두 통과하고, 새 코드가 기존 모듈의 책임을 침범하지 않아야 완료입니다.

