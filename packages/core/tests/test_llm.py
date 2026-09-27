"""The LLM door: fake scripting, SDK response parsing, model selection."""

from __future__ import annotations

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from novaxis_core.llm import FakeLLM, ToolCall, model_for, parse_response


def test_fake_llm_consumes_script_then_defaults() -> None:
    fake = FakeLLM(
        script=[("hello", [ToolCall("extract_fields", {"fields": {"name": "Al"}}, "t1")])]
    )
    r1 = fake.complete(
        task="worker_turn", system_stable="s", system_volatile="v", messages=[], tools=[]
    )
    r2 = fake.complete(
        task="worker_turn", system_stable="s", system_volatile="v", messages=[], tools=[]
    )
    assert r1.text == "hello" and r1.tool_calls[0].name == "extract_fields"
    assert r2.text == fake.default_text and r2.tool_calls == []
    assert len(fake.calls) == 2


def test_parse_response_reads_text_and_tool_use_blocks() -> None:
    msg = Message(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-sonnet-5",
        stop_reason="end_turn",
        stop_sequence=None,
        content=[
            TextBlock(type="text", text="Sure, "),
            ToolUseBlock(
                type="tool_use", id="tu_1", name="extract_fields", input={"fields": {"name": "Al"}}
            ),
            TextBlock(type="text", text="what time suits?"),
        ],
        usage=Usage(
            input_tokens=120,
            output_tokens=30,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=0,
        ),
    )
    r = parse_response(msg, latency_ms=42)
    assert r.text == "Sure,\nwhat time suits?"
    assert r.tool_calls == [ToolCall("extract_fields", {"fields": {"name": "Al"}}, "tu_1")]
    assert (r.input_tokens, r.output_tokens, r.cache_read_tokens, r.latency_ms) == (
        120,
        30,
        100,
        42,
    )


def test_model_selection_by_task(monkeypatch) -> None:
    from novaxis_core.settings import get_settings

    monkeypatch.setenv("NOVAXIS_MODEL_WORKER", "claude-opus-5")
    get_settings.cache_clear()
    try:
        assert model_for("worker_turn") == "claude-opus-5"
        assert model_for("classify") == "claude-haiku-4-5"
    finally:
        get_settings.cache_clear()


# --- Open-source and low-cost models through the OpenAI-compatible API --------------------

import json as _json  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from novaxis_core.llm import OpenAICompatLLM, build_llm  # noqa: E402
from novaxis_core.settings import get_settings  # noqa: E402

TOOL = {
    "name": "propose_appointment",
    "description": "Offer times",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"service_code": {"type": "string"}},
        "required": ["service_code"],
        "additionalProperties": False,
    },
}


def _open_model(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    base = {
        "NOVAXIS_LLM_PROVIDER": "openai_compatible",
        "NOVAXIS_LLM_BASE_URL": "http://models.test/v1/",
        "NOVAXIS_LLM_API_KEY": "k-123",
        "NOVAXIS_MODEL_WORKER": "open-worker",
        "NOVAXIS_MODEL_CLASSIFY": "open-small",
        "NOVAXIS_MODEL_SUMMARISE": "open-small",
        "NOVAXIS_LLM_MAX_RETRIES": "2",
        **env,
    }
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def _reply(content: str | None, calls: list[dict] | None = None, finish: str = "stop") -> dict:  # type: ignore[type-arg]
    return {
        "id": "chatcmpl-1",
        "model": "open-worker",
        "choices": [
            {
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, "tool_calls": calls},
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }


def test_open_model_request_has_the_system_prompt_messages_and_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open_model(monkeypatch)
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_reply("Hello"))

    llm = OpenAICompatLLM(transport=httpx.MockTransport(handler))
    r = llm.complete(
        task="worker_turn",
        system_stable="STABLE",
        system_volatile="VOLATILE",
        messages=[{"role": "user", "content": "hi"}],
        tools=[TOOL],
        max_tokens=300,
    )
    req = seen[0]
    body = _json.loads(req.content)
    assert str(req.url) == "http://models.test/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer k-123"
    assert body["model"] == "open-worker" and body["max_tokens"] == 300
    assert body["messages"][0] == {"role": "system", "content": "STABLE\n\nVOLATILE"}
    assert body["messages"][1] == {"role": "user", "content": "hi"}
    fn = body["tools"][0]["function"]
    assert fn["name"] == "propose_appointment" and fn["parameters"] == TOOL["input_schema"]
    assert "strict" not in _json.dumps(body["tools"]), "many open-model servers reject it"
    assert body["tool_choice"] == "auto"
    assert r.text == "Hello" and r.input_tokens == 120 and r.stop_reason == "end_turn"


def test_open_model_tool_calls_are_parsed_and_thinking_never_reaches_the_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open_model(monkeypatch)
    calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "propose_appointment",
                "arguments": '{"service_code": "repair_visit"}',
            },
        },
        {
            "id": "call_2",
            "type": "function",
            "function": {"name": "broken", "arguments": "{not json"},
        },
    ]
    content = "<think>The customer seems annoyed, I should upsell.</think>I can book that for you."

    llm = OpenAICompatLLM(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=_reply(content, calls, "tool_calls"))
        )
    )
    r = llm.complete(task="worker_turn", system_stable="s", system_volatile="", messages=[])
    assert r.text == "I can book that for you."
    assert [(c.name, c.input) for c in r.tool_calls] == [
        ("propose_appointment", {"service_code": "repair_visit"})
    ], "a call with broken arguments is dropped, never guessed"
    assert r.stop_reason == "tool_use"


def test_open_model_retries_busy_servers_but_not_bad_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open_model(monkeypatch)
    monkeypatch.setattr("novaxis_core.llm.time.sleep", lambda s: None)
    answers = iter(
        [httpx.Response(429), httpx.Response(503), httpx.Response(200, json=_reply("ok"))]
    )
    llm = OpenAICompatLLM(transport=httpx.MockTransport(lambda req: next(answers)))
    assert (
        llm.complete(task="classify", system_stable="s", system_volatile="", messages=[]).text
        == "ok"
    )

    hits: list[int] = []

    def bad(req: httpx.Request) -> httpx.Response:
        hits.append(1)
        return httpx.Response(400, json={"error": "bad"})

    llm = OpenAICompatLLM(transport=httpx.MockTransport(bad))
    with pytest.raises(httpx.HTTPStatusError):
        llm.complete(task="classify", system_stable="s", system_volatile="", messages=[])
    assert len(hits) == 1


def test_provider_switch_needs_open_model_names(monkeypatch: pytest.MonkeyPatch) -> None:
    _open_model(monkeypatch)
    assert isinstance(build_llm(), OpenAICompatLLM)
    _open_model(monkeypatch, NOVAXIS_MODEL_WORKER="claude-sonnet-5")
    with pytest.raises(RuntimeError, match="NOVAXIS_MODEL_WORKER"):
        build_llm()
    monkeypatch.setenv("NOVAXIS_LLM_PROVIDER", "nonsense")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="unknown"):
        build_llm()
