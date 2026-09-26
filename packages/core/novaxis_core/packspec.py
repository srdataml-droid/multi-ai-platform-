"""The minimal pack contract the worker needs today.

Chunk 5 replaces the constants with a loader over `packages/packs/<id>/`, but the
shape the worker depends on stays this one: a system prompt, a tool list, a first
intake question, and hard-coded emergency phrases checked before any LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PackSpec:
    id: str
    system_prompt: str
    tools: list[dict[str, Any]]
    intake_opening: str
    emergency_keywords: tuple[str, ...] = ()
    emergency_reply: str = ""
    vocabulary: dict[str, str] = field(default_factory=dict)


def proposal_tool(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    """A strict tool schema. The model proposes; the gate decides."""
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


# Tools every pack offers. Packs add their own in Chunk 5.
CORE_TOOLS: list[dict[str, Any]] = [
    proposal_tool(
        "extract_fields",
        "Record facts the customer has given (name, problem, address, preferred time). "
        "Call this whenever you learn something new. Keys are snake_case.",
        {"fields": {"type": "object", "additionalProperties": {"type": "string"}}},
        ["fields"],
    ),
    proposal_tool(
        "propose_appointment",
        "Propose an appointment once intake is complete. A staff member approves it before "
        "anything is booked, so never tell the customer it is booked.",
        {
            "service_code": {"type": "string"},
            "preferred_window": {
                "type": "string",
                "description": "Customer's words, e.g. 'Tuesday morning'",
            },
            "notes": {"type": "string"},
        },
        ["service_code", "preferred_window", "notes"],
    ),
    proposal_tool(
        "hand_to_human",
        "Stop and hand the conversation to a staff member. Use when the customer asks for a "
        "person, is upset, or asks something outside your remit.",
        {"reason": {"type": "string"}},
        ["reason"],
    ),
    proposal_tool(
        "escalate_emergency",
        "Alert the on-call contact immediately. Use for danger to life or property.",
        {"summary": {"type": "string"}},
        ["summary"],
    ),
]
