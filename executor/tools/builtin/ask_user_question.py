"""
ask_user_question — Let the AI ask the user structured questions and block until answered.

The tool sends a `question_ask` SSE event to the frontend via BackendCallback,
then blocks on Redis BLPOP waiting for the user's answer.

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""
from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog

from executor.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from executor.callbacks.backend_callback import BackendCallback

logger = structlog.get_logger()

_QUESTION_TIMEOUT_S = 300  # 5 minutes, matches frontend countdown


class AskUserQuestionTool(BaseTool):
    """Ask the user one or more structured questions and wait for their answers.

    Sends a question_ask event to the frontend, which renders a modal.
    Blocks until the user submits answers or the 5-minute timeout expires.

    capabilities: [] — no special capability required (interactive, no side effects)
    """

    capabilities: list[str] = []

    def __init__(self, callback: "BackendCallback") -> None:
        self._callback = callback

    @property
    def name(self) -> str:
        return "ask_user_question"

    @property
    def description(self) -> str:
        return (
            "Ask the user one or more structured questions and wait for their answers. "
            "Use when you need user input, clarification, or a decision before proceeding. "
            "Each question can have selectable options (single or multi-select) plus a free-text 'Other' field."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "List of questions to ask the user.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question text.",
                            },
                            "header": {
                                "type": "string",
                                "description": "Short header/title shown above the question.",
                            },
                            "options": {
                                "type": "array",
                                "description": "Selectable option cards.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["label"],
                                },
                            },
                            "multiSelect": {
                                "type": "boolean",
                                "description": "Whether multiple options can be selected.",
                                "default": False,
                            },
                        },
                        "required": ["question"],
                    },
                    "minItems": 1,
                }
            },
            "required": ["questions"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        questions = tool_input.get("questions")
        if not questions or not isinstance(questions, list):
            return ToolResult(content="Error: questions is required and must be a non-empty list", is_error=True)

        request_id = str(uuid.uuid4())
        redis_key = f"ask:question:{request_id}"

        await self._callback._http_post_with_retry(
            "question_ask",
            {
                "request_id": request_id,
                "questions": questions,
            },
        )

        logger.info("ask_user_question.waiting", request_id=request_id)

        result = await self._callback._redis.blpop(redis_key, timeout=_QUESTION_TIMEOUT_S)
        if result is None:
            logger.warning("ask_user_question.timeout", request_id=request_id)
            return ToolResult(content="User did not answer within the timeout.", is_error=False)

        raw = result[1]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        logger.info("ask_user_question.answered", request_id=request_id)
        return ToolResult(content=raw)
