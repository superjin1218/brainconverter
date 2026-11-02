"""Field identifier syntax only; no dataset catalog, aliases or indicator mapping."""

import keyword
import re

DATA_FIELD_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"
GROUP_IDENTIFIERS = frozenset({"industry", "sector", "subindustry"})


def is_data_field(name: str) -> bool:
    return (
        isinstance(name, str)
        and 1 <= len(name) <= 128
        and re.fullmatch(DATA_FIELD_PATTERN, name) is not None
        and not keyword.iskeyword(name)
        and name not in GROUP_IDENTIFIERS
    )


def validate_data_field(name: str) -> str:
    if not is_data_field(name):
        raise ValueError("데이터 필드는 영문자로 시작하는 필드 식별자여야 합니다.")
    return name
