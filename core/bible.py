"""Bible generation: one structured prompt, strict schema check, one retry."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LINES_RANGE = (5, 8)
PALETTE_RANGE = (4, 6)
LANG_NAMES = {"en": "English", "ko": "Korean"}
TEXT_FIELDS = ("name", "background", "world", "master_prompt")

SYSTEM_PROMPT = """You are a lore designer who returns machine-readable character bibles.

Return ONLY one JSON object. No prose, no markdown fences, no trailing commentary.
The object must match this shape exactly:

{
  "name": "character name",
  "profile": {"age": "str", "role": "str", "body": "str", "traits": ["str", ...]},
  "background": "two to four sentences of history",
  "voice": {"personality": "str", "speech": "str"},
  "lines": [{"situation": "str", "line": "str"}],
  "palette": [{"hex": "#RRGGBB", "name": "str"}],
  "world": "two to four sentences about the setting",
  "master_prompt": "English image-board prompt"
}

Rules:
- "lines" holds 5 to 8 signature quotes, each with the situation that prompts it.
- "palette" holds 4 to 6 colors; every "hex" is exactly #RRGGBB.
- "master_prompt" is ALWAYS English, regardless of the body language."""

USER_TEMPLATE = """Concept: {concept}
Art style: {style}
Board density: {density} sections
Body language: {lang_name}

Write the bible body ({lang_name}) for this concept.

"master_prompt" describes ONE single character-sheet image laid out as a grid of
{density} labelled sections (expressions, poses, props, outfit details, and
close-ups as needed), rendered in the {style} style. Name the layout, the
sections, the character's look and the palette in it. Write it in English."""

CORRECTION = """Your previous reply was rejected: {error}

Return ONLY the corrected JSON object. No fences, no explanation, no extra keys."""


class BibleParseError(Exception):
    """The model never produced a valid bible. `raw` holds the last reply."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def build_prompt(concept: str, style: str, density: int, lang: str) -> Tuple[str, str]:
    user = USER_TEMPLATE.format(
        concept=concept,
        style=style or "artist's choice",
        density=density,
        lang_name=LANG_NAMES.get(lang, LANG_NAMES["en"]),
    )
    return SYSTEM_PROMPT, user


def extract_json(text: str) -> str:
    """Drop a markdown fence around the payload when the model adds one."""
    body = (text or "").strip()
    if not body.startswith("```"):
        return body
    body = body[3:]
    head, _, rest = body.partition("\n")
    if head.strip() and not head.strip().startswith("{"):
        body = rest
    closing = body.rfind("```")
    if closing != -1:
        body = body[:closing]
    return body.strip()


def parse_bible(raw: str) -> Dict[str, Any]:
    """Decode and validate one model reply. Raises ValueError on any defect."""
    try:
        data = json.loads(extract_json(raw))
    except json.JSONDecodeError as err:
        raise ValueError(f"response is not valid JSON ({err})") from err
    validate_bible(data)
    return data


def validate_bible(data: Any) -> None:
    """Raise ValueError listing every schema violation found."""
    if not isinstance(data, dict):
        raise ValueError("bible must be a JSON object")
    errors: List[str] = []
    for field in TEXT_FIELDS:
        _text(data.get(field), field, errors)
    _profile(data.get("profile"), errors)
    _voice(data.get("voice"), errors)
    _lines(data.get("lines"), errors)
    _palette(data.get("palette"), errors)
    if errors:
        raise ValueError("; ".join(errors))


def generate_bible(
    concept: str, style: str, density: int, lang: str, llm: Any
) -> Dict[str, Any]:
    """Ask the model for a bible, retrying once with the validation error."""
    system, user = build_prompt(concept, style, density, lang)
    prompt = user
    raw = ""
    problem = "no response"
    for _ in range(2):
        raw = llm.generate(system, prompt)
        try:
            return parse_bible(raw)
        except ValueError as err:
            problem = str(err)
            prompt = f"{user}\n\n{CORRECTION.format(error=problem)}"
    raise BibleParseError(problem, raw=raw)


# -- schema helpers ------------------------------------------------------
def _text(value: Any, field: str, errors: List[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")
        return False
    return True


def _object(value: Any, field: str, errors: List[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return False
    return True


def _entries(value: Any, field: str, bounds: Tuple[int, int], errors: List[str]) -> List[Any]:
    low, high = bounds
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    if not low <= len(value) <= high:
        errors.append(f"{field} must have {low}-{high} entries (got {len(value)})")
    return value


def _profile(value: Any, errors: List[str]) -> None:
    if not _object(value, "profile", errors):
        return
    for key in ("age", "role", "body"):
        _text(value.get(key), f"profile.{key}", errors)
    traits = value.get("traits")
    if not isinstance(traits, list) or not traits:
        errors.append("profile.traits must be a non-empty array")
        return
    for index, trait in enumerate(traits):
        _text(trait, f"profile.traits[{index}]", errors)


def _voice(value: Any, errors: List[str]) -> None:
    if not _object(value, "voice", errors):
        return
    for key in ("personality", "speech"):
        _text(value.get(key), f"voice.{key}", errors)


def _lines(value: Any, errors: List[str]) -> None:
    for index, entry in enumerate(_entries(value, "lines", LINES_RANGE, errors)):
        if not _object(entry, f"lines[{index}]", errors):
            continue
        _text(entry.get("situation"), f"lines[{index}].situation", errors)
        _text(entry.get("line"), f"lines[{index}].line", errors)


def _palette(value: Any, errors: List[str]) -> None:
    for index, entry in enumerate(_entries(value, "palette", PALETTE_RANGE, errors)):
        if not _object(entry, f"palette[{index}]", errors):
            continue
        _text(entry.get("name"), f"palette[{index}].name", errors)
        hex_value = entry.get("hex")
        if not isinstance(hex_value, str) or not HEX_RE.match(hex_value):
            errors.append(f"palette[{index}].hex must match #RRGGBB")
