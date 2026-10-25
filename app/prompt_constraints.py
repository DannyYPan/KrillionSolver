"""Parse exclusions embedded in game prompts."""

from __future__ import annotations

import re

_DOES_NOT_COUNT = r"(?:doesn't|does not|doesnt|don't|do not|isn't|is not)\s+count"


def split_prompt_exclusions(prompt: str) -> tuple[str, list[str]]:
    """Return the answerable prompt and any explicitly disallowed answers."""
    patterns = (
        re.compile(rf"\s*\((?P<excluded>[^()]*)\s+{_DOES_NOT_COUNT}\b[^)]*\)\s*$", re.I),
        re.compile(rf"\s+(?:[—–-]\s+|;\s*|,\s*)(?P<excluded>.+?)\s+{_DOES_NOT_COUNT}\b[^.!?]*[.!?]*$", re.I),
        re.compile(r"\s+\b(?:excluding|except for|except|but not|not including)\s+(?P<excluded>[^.!?;]+)[.!?]*$", re.I),
    )
    core = prompt.strip()
    excluded: list[str] = []
    for pattern in patterns:
        match = pattern.search(core)
        if not match:
            continue
        raw = re.sub(r"^\s*but\s+", "", match.group("excluded"), flags=re.I)
        excluded.extend(
            re.sub(r"^(?:a|an|the)\s+", "", part.strip(" .,!?:;—–-"), flags=re.I)
            for part in re.split(r",|\band\b|\bor\b", raw, flags=re.I)
        )
        core = core[:match.start()].rstrip(" ,;—–-")
        break
    return core, [item for item in excluded if item]
