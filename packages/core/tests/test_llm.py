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
