"""
json_repairer.py — Extract valid JSON from raw LLM output.

LLMs often wrap JSON in markdown fences (```json ... ```) or add explanation
text before/after the JSON object. This module strips the noise and returns
a parsed dict, tracking whether repair was needed.
"""
from __future__ import annotations

import json
import re


class JSONRepairError(ValueError):
    """Raised when no valid JSON can be extracted from the LLM response."""


def repair_json(raw: str) -> tuple[dict, bool]:
    """
    Parse a JSON dict from raw LLM output.

    Returns:
        (parsed_dict, was_repaired)
        was_repaired is True if the raw text required stripping before parsing.

    Raises:
        JSONRepairError if no valid JSON object can be found.
    """
    if not raw or not raw.strip():
        raise JSONRepairError("LLM returned an empty response.")

    # Strategy 1: direct parse (clean JSON response)
    try:
        result = json.loads(raw.strip())
        if isinstance(result, dict):
            return result, False
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from ```json ... ``` or ``` ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result, True
        except json.JSONDecodeError:
            pass

    # Strategy 3: find the outermost { ... } span
    brace_match = re.search(r"\{[\s\S]*\}", raw)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result, True
        except json.JSONDecodeError:
            pass

    raise JSONRepairError(
        f"Could not extract valid JSON from LLM response "
        f"(first 200 chars): {raw[:200]!r}"
    )
