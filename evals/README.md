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

기본 실제 평가 상한은 한 사례입니다. `--limit`를 늘리면 사례당 한 번씩 유료 호출합니다. 고정 모델·추론 수준은 `backend/app/openai_policy.py`를 따르며 자동 재시도하지 않습니다. 화면에 입력한 메모리 키는 평가 터미널에 전달되지 않습니다. 실제 호출 여부와 결과는 `docs/SESSION_CONTEXT.md`와 해당 PR 기록에서 별도로 확인합니다.

결과 파일은 `artifacts/evaluation.json`이며 비용·토큰·상태·기대 코드 일치를 기록합니다. 기대 코드 일치만으로 모델의 일반화 성능을 주장하지 않습니다.

새 운영 요청은 AI가 설계한 `IntentIR`입니다. `backend/tests/test_intent_alignment.py`는 독립적인 응답으로 원문 근거·선호 방향·임의 점수식 차단을 검사합니다. `test_drafts.py`는 기존 AST 경계 호환 검증입니다. 이전 평가 사례의 기대식은 구형 컴파일러 기준이므로 새 순위 방향 표현(예: `1 - rank(x)`와 `rank(-x)`)의 의미가 같아도 문자열 기반 평가는 불일치로 표시할 수 있습니다. 실제 평가에서는 원문과 계획·코드의 대응도 별도로 검토해야 합니다. 이 테스트의 통과는 AI가 해당 응답을 실제로 생성했다는 의미가 아닙니다. 괄호·숫자 표기·교환 가능한 산술 연산의 순서만 다른 동치식은 실제 평가에서 같은 식으로 비교합니다.
