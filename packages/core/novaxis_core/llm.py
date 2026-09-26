"""One thin door to the language model.

Why this exists: every LLM call in the system goes through `LLMClient.complete`,
so cost accounting, timeouts, retries, model selection and tracing live in one
place, and every test can swap in `FakeLLM` and script the answer.

The worker turn is deliberately not an agentic loop. The model is given
*proposal* tools; each tool call becomes a row in `action_proposals` and the
gate decides what happens (Chunk 4). Nothing is executed inside the LLM call.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from novaxis_core.settings import get_settings

log = logging.getLogger("novaxis.llm")

Task = Literal["worker_turn", "classify", "summarise"]


@dataclass(frozen=True)
class ToolCall:
    name: str
    input: dict[str, Any]
    id: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    tool_calls: list[ToolCall]
    model: str
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    request_id: str | None = None


@dataclass
class Trace:
    """What we record about one call. Sensitive text is never included."""

    task: str
    model: str
    tenant_id: str
    conversation_id: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    latency_ms: int
    tool_calls: list[str]
    stop_reason: str | None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


Tracer = Callable[[Trace], None]


def log_tracer(trace: Trace) -> None:
    log.info("llm %s", json.dumps(trace.__dict__, default=str, sort_keys=True))


class LLMClient(Protocol):
    def complete(
        self,
        *,
        task: Task,
        system_stable: str,
        system_volatile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResult: ...


def model_for(task: Task) -> str:
    s = get_settings()
    return {
        "worker_turn": s.model_worker,
        "classify": s.model_classify,
        "summarise": s.model_summarise,
    }[task]


class AnthropicLLM:
    """Real calls through the official SDK.

    Caching: the pack's stable system prompt carries a cache breakpoint; tenant
    facts and anything that changes per turn come after it. Thinking stays at
    the model's adaptive default with low effort, because a front-desk reply
    should be quick and short; evals (Chunk 13) can raise it per pack.
    """

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            import anthropic

            s = get_settings()
            client = anthropic.Anthropic(
                timeout=s.llm_timeout_seconds, max_retries=s.llm_max_retries
            )
        self._client = client

    def complete(
        self,
        *,
        task: Task,
        system_stable: str,
        system_volatile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResult:
        model = model_for(task)
        system: list[dict[str, Any]] = [
            {"type": "text", "text": system_stable, "cache_control": {"type": "ephemeral"}}
        ]
        if system_volatile:
            system.append({"type": "text", "text": system_volatile})
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "output_config": {"effort": "low"},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "auto"}
        started = time.monotonic()
        response = self._client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - started) * 1000)
        return parse_response(response, latency_ms)


def parse_response(response: Any, latency_ms: int = 0) -> LLMResult:
    """Turn an SDK Message into our result. Tool inputs are already parsed dicts."""
    texts: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            texts.append(block.text)
        elif block.type == "tool_use":
            raw = block.input
            parsed = raw if isinstance(raw, dict) else json.loads(raw)
            calls.append(ToolCall(name=block.name, input=parsed, id=block.id))
    usage = getattr(response, "usage", None)
    return LLMResult(
        text="\n".join(t.strip() for t in texts if t.strip()).strip(),
        tool_calls=calls,
        model=str(getattr(response, "model", "")),
        stop_reason=getattr(response, "stop_reason", None),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        latency_ms=latency_ms,
        request_id=getattr(response, "_request_id", None),
    )


class FakeLLM:
    """Scripted answers for tests and offline demos.

    `script` is a list of (text, tool_calls) consumed in order; when it runs out the
    default reply is returned. Every call is recorded in `calls` so tests can assert
    what the model was shown without a network.
    """

    def __init__(
        self,
        script: list[tuple[str, list[ToolCall]]] | None = None,
        default_text: str = "Thanks for your message. How can we help today?",
    ) -> None:
        self.script = list(script or [])
        self.default_text = default_text
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        task: Task,
        system_stable: str,
        system_volatile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResult:
        self.calls.append(
            {
                "task": task,
                "system_stable": system_stable,
                "system_volatile": system_volatile,
                "messages": messages,
                "tools": [t["name"] for t in tools or []],
            }
        )
        if task == "summarise":
            return LLMResult(
                text="Summary: customer conversation so far.",
                tool_calls=[],
                model="fake",
                stop_reason="end_turn",
            )
        text, calls = self.script.pop(0) if self.script else (self.default_text, [])
        return LLMResult(
            text=text,
            tool_calls=calls,
            model="fake",
            stop_reason="end_turn",
            input_tokens=10,
            output_tokens=5,
        )


def build_llm() -> LLMClient:
    s = get_settings()
    if s.llm_provider == "fake":
        return FakeLLM()
    return AnthropicLLM()
