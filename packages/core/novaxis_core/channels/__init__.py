"""Channel registry. Add a channel here and in `TenantSettings.channels`."""

from __future__ import annotations

from novaxis_core.channels.base import (
    ChannelAdapter,
    InboundRequest,
    Media,
    NormalisedInbound,
    ParseError,
    ProviderRef,
    SignatureError,
)
from novaxis_core.channels.email_postmark import PostmarkEmailAdapter
from novaxis_core.channels.twilio_sms import TwilioSmsAdapter
from novaxis_core.channels.twilio_voice import TwilioVoiceAdapter
from novaxis_core.channels.webchat import WebchatAdapter

_ADAPTERS: dict[str, ChannelAdapter] = {
    "webchat": WebchatAdapter(),
    "twilio_sms": TwilioSmsAdapter(),
    "twilio_voice": TwilioVoiceAdapter(),
    "email": PostmarkEmailAdapter(),
}


def get_adapter(channel: str) -> ChannelAdapter:
    try:
        return _ADAPTERS[channel]
    except KeyError as exc:
        raise KeyError(f"unknown channel {channel!r}") from exc


def register_adapter(adapter: ChannelAdapter) -> None:
    """Tests swap in adapters with fake transports."""
    _ADAPTERS[adapter.channel] = adapter


__all__ = [
    "ChannelAdapter",
    "InboundRequest",
    "Media",
    "NormalisedInbound",
    "ParseError",
    "ProviderRef",
    "SignatureError",
    "get_adapter",
    "register_adapter",
]
