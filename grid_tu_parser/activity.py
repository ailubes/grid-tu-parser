from __future__ import annotations

from .normalize import normalize_text


def normalize_activity(value: str) -> str:
    text = normalize_text(value or "").lower()

    if "узе" in text or "зберігання енергі" in text or "накопичува" in text:
        return "bess"

    generation_markers = (
        "генерац",
        "виробництв",
        "виробник",
    )
    consumption_markers = (
        "споживан",
        "споживач",
        "навантажен",
    )

    has_generation = any(marker in text for marker in generation_markers)
    has_consumption = any(marker in text for marker in consumption_markers)

    if has_generation and has_consumption:
        return "mixed"
    if has_generation:
        return "generation"
    if has_consumption:
        return "consumption"
    return "unknown"
