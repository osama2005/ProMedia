"""Smart download rules: conditions -> destination / quality actions.

The rule engine is deliberately pure so it can be tested without a UI or a
network connection.  Rules are plain JSON-friendly dictionaries persisted in
``Settings.download_rules``.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

VALID_CONDITIONS = ("kind", "size", "speed", "platform", "keyword")
VALID_ACTIONS = ("subdir", "max_height", "audio_only")
KIND_VALUES = ("video", "audio")

_SIZE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(B|KB|KIB|MB|MIB|GB|GIB|TB)", re.I)
_SIZE_FACTORS = {
    "B": 1,
    "KB": 1024,
    "KIB": 1024,
    "MB": 1024 ** 2,
    "MIB": 1024 ** 2,
    "GB": 1024 ** 3,
    "GIB": 1024 ** 3,
    "TB": 1024 ** 4,
}


# Four ready-made rules.  All start disabled so existing download behaviour is
# unchanged until the user opts in from the Rules settings tab.
DEFAULT_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "kind_video",
        "name": "",
        "name_key": "rule_kind_video",
        "enabled": False,
        "condition": "kind",
        "value": "video",
        "action": "subdir",
        "action_value": "Video",
    },
    {
        "id": "kind_audio",
        "name": "",
        "name_key": "rule_kind_audio",
        "enabled": False,
        "condition": "kind",
        "value": "audio",
        "action": "subdir",
        "action_value": "Audio",
    },
    {
        "id": "large_files",
        "name": "",
        "name_key": "rule_large_files",
        "enabled": False,
        "condition": "size",
        "value": 200,
        "action": "subdir",
        "action_value": "Large Files",
    },
    {
        "id": "slow_quality",
        "name": "",
        "name_key": "rule_slow_quality",
        "enabled": False,
        "condition": "speed",
        "value": 500,
        "action": "max_height",
        "action_value": 720,
    },
)


def parse_size_text(text: str) -> int:
    """Convert a human size such as ``"48.2 MB"`` to bytes (0 when unknown)."""
    match = _SIZE_RE.search(str(text or ""))
    if not match:
        return 0
    factor = _SIZE_FACTORS.get(match.group(2).upper(), 0)
    if not factor:
        return 0
    try:
        return int(float(match.group(1)) * factor)
    except ValueError:
        return 0


def safe_folder_name(value: str) -> str:
    """Sanitise a rule-provided folder name (no separators or traversal)."""
    text = re.sub(r"[^\w\- ]+", "_", str(value or ""), flags=re.UNICODE)
    text = text.strip(" ._")[:60]
    if text in ("..", ".") or not text:
        return "Media"
    return text


def _int_value(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def sanitize_rules(raw: Any) -> list[dict[str, Any]]:
    """Return a clean, bounded rule list usable by both UI and engine."""
    if not isinstance(raw, list):
        return [dict(rule) for rule in DEFAULT_RULES]
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:40]):
        if not isinstance(item, dict):
            continue
        condition = str(item.get("condition") or "").strip().lower()
        action = str(item.get("action") or "").strip().lower()
        if condition not in VALID_CONDITIONS or action not in VALID_ACTIONS:
            continue
        rule: dict[str, Any] = {
            "id": str(item.get("id") or f"rule-{index + 1}")[:60],
            "name": str(item.get("name") or "")[:80],
            "name_key": str(item.get("name_key") or "")[:80],
            "enabled": bool(item.get("enabled", False)),
            "condition": condition,
            "action": action,
        }
        if condition == "kind":
            value = str(item.get("value") or "video").strip().lower()
            rule["value"] = value if value in KIND_VALUES else "video"
        elif condition == "size":
            rule["value"] = _int_value(item.get("value"), 200, 1, 100000)
        elif condition == "speed":
            rule["value"] = _int_value(item.get("value"), 500, 1, 1000000)
        else:
            rule["value"] = str(item.get("value") or "")[:60]

        if action == "subdir":
            rule["action_value"] = safe_folder_name(item.get("action_value"))
        elif action == "max_height":
            rule["action_value"] = _int_value(item.get("action_value"), 720, 144, 4320)
        else:
            rule["action_value"] = ""
        result.append(rule)
    return result


def rule_label(rule: dict[str, Any]) -> str:
    """Human-readable rule name; translation happens in the UI layer."""
    return str(rule.get("name") or rule.get("name_key") or rule.get("id") or "Rule")


def matches(
    rule: dict[str, Any],
    *,
    mode: str = "video",
    approx_bytes: int = 0,
    speed_kbps: float = 0.0,
    platform: str = "",
    title: str = "",
) -> bool:
    """Return True when a rule's condition is satisfied."""
    if not rule.get("enabled"):
        return False
    condition = rule.get("condition")
    value = rule.get("value")
    if condition == "kind":
        return str(value).lower() == str(mode).lower()
    if condition == "size":
        # Unknown size must never trigger a size rule.
        return approx_bytes > 0 and approx_bytes >= int(value) * 1024 * 1024
    if condition == "speed":
        # No active download yet means speed is unknown, not "slow".
        return 0 < speed_kbps <= float(value)
    if condition == "platform":
        needle = str(value).strip().lower()
        return bool(needle) and needle in str(platform).lower()
    if condition == "keyword":
        needle = str(value).strip().lower()
        return bool(needle) and needle in str(title).lower()
    return False


def apply_rules(
    request: Any,
    rules: list[dict[str, Any]],
    *,
    approx_bytes: int = 0,
    speed_kbps: float = 0.0,
) -> tuple[Any, list[str]]:
    """Return a copy of *request* with matching rules applied and their labels.

    Rule ids already present in ``request.applied_rules`` are skipped, so a
    retry never nests the same folder twice or re-caps a height indefinitely.
    """
    updated = replace(request)
    applied: list[str] = []
    already = {
        item.strip()
        for item in str(getattr(updated, "applied_rules", "") or "").split(",")
        if item.strip()
    }
    used: list[str] = list(already)
    for rule in rules or []:
        rule_id = str(rule.get("id") or "")
        if rule_id in already:
            continue
        if not matches(
            rule,
            mode=str(getattr(updated, "mode", "") or ""),
            approx_bytes=approx_bytes,
            speed_kbps=speed_kbps,
            platform=str(getattr(updated, "platform", "") or ""),
            title=str(getattr(updated, "title", "") or ""),
        ):
            continue
        action = rule.get("action")
        if action == "subdir":
            base = Path(getattr(updated, "dest_dir", "") or "")
            updated.dest_dir = str(base / safe_folder_name(rule.get("action_value")))
        elif action == "max_height":
            limit = int(rule.get("action_value") or 720)
            if getattr(updated, "mode", "") == "video" and (
                not getattr(updated, "height", None)
                or int(updated.height) > limit
            ):
                updated.height = limit
        elif action == "audio_only":
            updated.mode = "audio"
            updated.height = None
        applied.append(rule_label(rule))
        if rule_id:
            used.append(rule_id)
    if applied or not already:
        updated.applied_rules = ",".join(used)
    return updated, applied
