from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent / "skills" / "brain-strategy" / "SKILL.md"
BASE_SYSTEM_PROMPT = SKILL_PATH.read_text(encoding="utf-8").split("---", 2)[2].strip()


def prepare_catalog_prompt(strategy, fields, operators, catalog_id, *, generation_budget=16840):
    import json

    from .catalog_context import catalog_context
    from .openai_policy import OPENAI_POLICY

    basic = [row for row in fields if row.id in {
        "open", "high", "low", "close", "volume", "returns",
    }]
    ranked = [row for row in fields if row not in basic]
    # Bind the exact same candidate set while measuring and while generating.
    best = None
    for count in range(len(ranked), -1, -1):
        chosen = tuple(basic + ranked[:count])
        rows = [[row.id, row.type, row.dataset, row.description[:120]] for row in chosen]
        prompt = (BASE_SYSTEM_PROMPT + "\nFIELD CANDIDATES [id,type,dataset,description]:\n"
                  + json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
        with catalog_context(chosen, operators, catalog_id,
                             generation_budget_microusd=generation_budget,
                             source_strategy=strategy):
            try:
                body = OPENAI_POLICY.payload(prompt, strategy)
            except RuntimeError:
                continue
        if len(chosen) >= min(8, len(fields)):
            best = prompt, chosen
            if body["max_completion_tokens"] == OPENAI_POLICY.max_completion_tokens:
                return best
            continue
        break
    if best is not None:
        return best
    raise RuntimeError("현재 입력과 필드 목록을 모델 입력 한도에 담을 수 없습니다.")
