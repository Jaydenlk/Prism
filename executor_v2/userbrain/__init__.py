from __future__ import annotations


def normalize_openai_base_url(raw: str) -> str:
    base = (raw or "").rstrip("/")
    if "/anthropic" in base:
        base = base.replace("/anthropic", "")
    return f"{base}/v1" if base else "https://api.anthropic.com/v1"
