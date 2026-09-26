"""The shape every channel must fit.

A channel adapter turns a provider's webhook into one `NormalisedInbound`, and
turns one outbound message into a provider call. Nothing else. Contact matching,
conversation threading and job creation live in `novaxis_core.inbound`, so a new
channel is a small file, not a rewrite.

Adapters take an `InboundRequest`, a plain value object, so the core never
imports a web framework and adapters are testable with a dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class InboundRequest:
    """What the API hands an adapter: enough to verify and parse, nothing more."""

    url: str
    headers: dict[str, str]
    form: dict[str, str] = field(default_factory=dict)
    json: dict[str, Any] | None = None
    query: dict[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        for k, v in self.headers.items():
            if k.lower() == wanted:
                return v
        return None


class Media(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    content_type: str | None = None


class NormalisedInbound(BaseModel):
    """One inbound message, provider details stripped away."""

    model_config = ConfigDict(extra="forbid")

    channel: str
    provider_ref: str = Field(description="Provider's message id; idempotency key")
    tenant_ref: str = Field(description="How to find the tenant: To number, inbound address, slug")
    sender_phone: str | None = None
    sender_email: str | None = None
    sender_visitor_id: str | None = None
    sender_name: str | None = None
    body: str
    media: list[Media] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw: dict[str, Any] = Field(default_factory=dict, description="Non-sensitive provider extras")


@dataclass(frozen=True)
class ProviderRef:
    provider_ref: str


class ChannelAdapter(Protocol):
    channel: str

    def verify_signature(self, request: InboundRequest) -> bool: ...

    def parse_inbound(self, request: InboundRequest) -> NormalisedInbound: ...

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef: ...


class SignatureError(Exception):
    """Raised by the API layer when verify_signature returns False."""


class ParseError(ValueError):
    """The payload is not what the provider documents."""
