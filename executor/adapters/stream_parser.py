"""
Prism v2 Model Adapter Layer — 公共 SSE 行解析器

两个 Driver(Anthropic / OpenAI)共用此解析器。
处理 SSE 协议:event:/data: 行分组,空行分隔事件,[DONE] 终止。
JSON 容错:先试 json_repair,失败则 yield error 事件并跳过。
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

try:
    import json_repair
    _HAS_JSON_REPAIR = True
except ImportError:  # pragma: no cover
    _HAS_JSON_REPAIR = False

logger = logging.getLogger(__name__)


async def parse_sse_lines(
    response: httpx.Response,
) -> AsyncIterator[tuple[str, dict]]:
    """
    解析 SSE 响应流,yield (event_type, data_dict)。

    协议规则:
    - `event: xxx` 行:设置当前事件类型(缺省为 "message")
    - `data: {...}` 行:JSON 解析为 data_dict
    - `data: [DONE]`:SSE 流正常结束,停止迭代
    - 空行:分隔事件,触发 yield
    - JSON 容错:先试 json_repair 修复,仍失败则 yield ("error", {...}) 并跳过

    Yields:
        (event_type, data_dict) — 每个完整 SSE 事件一次
    """
    current_event: str = "message"
    current_data: str | None = None

    async for line in response.aiter_lines():
        # 去除末尾空白
        line = line.rstrip()

        if not line:
            # 空行:当前事件结束
            if current_data is not None:
                data_str = current_data
                event_type = current_event
                # 重置状态
                current_event = "message"
                current_data = None

                if data_str == "[DONE]":
                    # OpenAI 流终止信号
                    return

                # JSON 解析(含容错)
                parsed = _parse_json_safe(data_str)
                if parsed is None:
                    # json_repair 也无法修复,发送 error 事件并跳过
                    logger.warning(
                        "SSE JSON parse failed, skipping line",
                        extra={"raw": data_str[:200]},
                    )
                    yield (
                        "error",
                        {
                            "type": "error",
                            "error": "json_parse_failed",
                            "raw": data_str[:500],
                        },
                    )
                    continue

                yield (event_type, parsed)
            continue

        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_part = line[len("data:"):].strip()
            if current_data is None:
                current_data = data_part
            else:
                # 多行 data(罕见但合法)
                current_data += "\n" + data_part
        # 其他行(comment ":", id: 等)忽略

    # 流结束时若有未 yield 的数据,也处理
    if current_data is not None and current_data != "[DONE]":
        parsed = _parse_json_safe(current_data)
        if parsed is not None:
            yield (current_event, parsed)


def _parse_json_safe(data: str) -> dict | None:
    """
    安全 JSON 解析:先标准 json.loads,失败则 json_repair 修复。
    两者均失败返回 None。
    """
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        pass

    if _HAS_JSON_REPAIR:
        try:
            repaired = json_repair.repair_json(data)
            result = json.loads(repaired)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, Exception):
            pass

    return None
