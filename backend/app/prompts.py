from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent / "skills" / "brain-strategy" / "SKILL.md"
BASE_SYSTEM_PROMPT = SKILL_PATH.read_text(encoding="utf-8").split("---", 2)[2].strip()
