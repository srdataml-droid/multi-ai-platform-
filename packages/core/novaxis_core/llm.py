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
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

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


_THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)
_FINISH = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}


class OpenAICompatLLM:
    """Open-source and low-cost models through the OpenAI-compatible chat API.

    Ollama (local), vLLM (self-hosted) and most hosted open-model services speak this
    format, so changing model or provider is three settings and no code:
    NOVAXIS_LLM_BASE_URL, NOVAXIS_MODEL_WORKER (and _CLASSIFY, _SUMMARISE),
    NOVAXIS_LLM_API_KEY.

    What is different from the Anthropic path, on purpose:
    - No prompt caching: the stable and volatile system text are sent as one system message.
    - Tool schemas are sent without `strict`, which many servers reject. The approval gate
      validates every tool input against its schema anyway, so a malformed call is
      refused there, never executed.
    - Reasoning models may put their thinking in the reply as <think>...</think>; it is
      removed, because it must never reach a customer.
    """

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        s = get_settings()
        self._base = s.llm_base_url.rstrip("/")
        self._retries = s.llm_max_retries
        headers = {"Content-Type": "application/json"}
        if s.llm_api_key:
            headers["Authorization"] = f"Bearer {s.llm_api_key}"
        self._client = httpx.Client(
            timeout=s.llm_timeout_seconds, headers=headers, transport=transport
        )

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
        system = system_stable if not system_volatile else f"{system_stable}\n\n{system_volatile}"
        body: dict[str, Any] = {
            "model": model_for(task),
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"
        started = time.monotonic()
        data = self._post(body)
        return parse_openai_response(data, int((time.monotonic() - started) * 1000))

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST with retries on rate limits, server errors and dropped connections only."""
        url = f"{self._base}/chat/completions"
        for attempt in range(self._retries + 1):
            last = attempt == self._retries
            try:
                r = self._client.post(url, json=body)
            except httpx.TransportError:
                if last:
                    raise
                time.sleep(min(2**attempt, 8))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if last:
                    r.raise_for_status()
                wait = r.headers.get("retry-after", "")
                time.sleep(min(float(wait) if wait.isdigit() else 2**attempt, 20))
                continue
            r.raise_for_status()
            result: dict[str, Any] = r.json()
            return result
        raise RuntimeError("unreachable")


def parse_openai_response(data: dict[str, Any], latency_ms: int = 0) -> LLMResult:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = _THINK.sub("", str(message.get("content") or "")).strip()
    calls: list[ToolCall] = []
    for i, tc in enumerate(message.get("tool_calls") or []):
        fn = tc.get("function") or {}
        raw = fn.get("arguments") or "{}"
        try:
            args = raw if isinstance(raw, dict) else json.loads(raw)
        except json.JSONDecodeError:
            log.warning("llm: dropped tool call %s with invalid JSON arguments", fn.get("name"))
            continue
        if not isinstance(args, dict) or not fn.get("name"):
            continue
        calls.append(ToolCall(name=str(fn["name"]), input=args, id=str(tc.get("id") or f"c{i}")))
    usage = data.get("usage") or {}
    finish = choice.get("finish_reason")
    return LLMResult(
        text=text,
        tool_calls=calls,
        model=str(data.get("model", "")),
        stop_reason=_FINISH.get(str(finish), finish),
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        cache_read_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        latency_ms=latency_ms,
        request_id=data.get("id"),
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
        return FakeLLM(script=script_from_env())
    if s.llm_provider == "openai_compatible":
        claude = [
            m
            for m in (s.model_worker, s.model_classify, s.model_summarise)
            if m.startswith("claude-")
        ]
        if claude:
            raise RuntimeError(
                "NOVAXIS_LLM_PROVIDER=openai_compatible needs open-model names: set "
                "NOVAXIS_MODEL_WORKER, NOVAXIS_MODEL_CLASSIFY and NOVAXIS_MODEL_SUMMARISE "
                f"(still set to {', '.join(claude)})"
            )
        return OpenAICompatLLM()
    if s.llm_provider == "anthropic":
        return AnthropicLLM()
    raise RuntimeError(f"unknown NOVAXIS_LLM_PROVIDER {s.llm_provider!r}")


def script_from_env() -> list[tuple[str, list[ToolCall]]]:
    """NOVAXIS_FAKE_SCRIPT: JSON list of {"text": ..., "calls": [{"tool": ..., "input": {...}}]}.
    Lets demos and end-to-end tests drive the worker without a model. Consumed per process."""
    import os

    raw = os.environ.get("NOVAXIS_FAKE_SCRIPT", "").strip()
    if not raw:
        return []
    out: list[tuple[str, list[ToolCall]]] = []
    for i, turn in enumerate(json.loads(raw)):
        calls = [
            ToolCall(c["tool"], c.get("input", {}), f"env{i}-{j}")
            for j, c in enumerate(turn.get("calls") or [])
        ]
        out.append((str(turn.get("text", "")), calls))
    return out
