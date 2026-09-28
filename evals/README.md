# 전략 변환 평가

오프라인 기본 평가:

```bash
.venv/bin/python scripts/evaluate.py
```

고정 규칙 Mock Provider와 기대 코드의 일치만 검사합니다. AI 해석 성능·BRAIN Simulate 성공·수익성을 평가하지 않습니다.

실제 평가는 `.env.local` 또는 프로세스 환경의 `OPENAI_API_KEY`를 사용합니다. 아래 명령을 직접 선택하면 유료 GPT 호출을 수행합니다.

```bash
.venv/bin/python scripts/evaluate.py --live --limit 1
```

기본 실제 평가 상한은 한 사례입니다. `--limit`를 늘리면 사례당 한 번씩 유료 호출합니다. 고정 모델·추론 수준은 `backend/app/openai_policy.py`를 따르며 자동 재시도하지 않습니다. 화면에 입력한 메모리 키는 평가 터미널에 전달되지 않습니다. 유료 평가는 이번 정리에서 실행하지 않았습니다.

결과 파일은 `artifacts/evaluation.json`이며 비용·토큰·상태·기대 코드 일치를 기록합니다. 기대 코드 일치만으로 모델의 일반화 성능을 주장하지 않습니다.
