# 전략 변환 평가

오프라인 기본 평가:

```bash
.venv/bin/python scripts/evaluate.py
```

고정 규칙 Mock Provider와 기대 코드의 일치만 검사합니다. AI 해석 성능·BRAIN Simulate 성공·수익성을 평가하지 않습니다.

실제 평가는 `AI_GATEWAY_API_KEY`를 안전한 환경변수로 주입한 뒤 아래 명령을 **직접 선택**해야 합니다. Contributor 입력·응답의 Meta 학습 활용 조건을 먼저 확인합니다. [Meta 조건](https://dev.meta.ai/docs/pricing-rate-limits).

```bash
.venv/bin/python scripts/evaluate.py --live --accept-contributor-terms --limit 1
```

기본 실제 평가 상한은 한 사례입니다. `--limit`를 늘리면 사례당 한 번씩 유료 호출합니다. 자동 재시도하지 않습니다. 새 Gateway 키만 사용하며 이전 OpenAI 키는 사용할 수 없습니다. 화면에 입력한 키는 평가 터미널에 전달되지 않습니다. 실제 실행을 이번 변경에서 수행하지 않았습니다.

결과 파일은 `artifacts/evaluation.json`이며 비용·토큰·상태·기대 코드 일치를 기록합니다. 기대 코드 일치만으로 모델의 일반화 성능을 주장하지 않습니다.
