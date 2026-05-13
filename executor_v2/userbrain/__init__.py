from __future__ import annotations


def normalize_openai_base_url(raw: str) -> str:
    base = (raw or "").rstrip("/")
    if base.endswith("/anthropic"):
        base = base[: -len("/anthropic")]
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return f"{base}/v1" if base else "/v1"
