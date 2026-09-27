"""Phone calls through Twilio Voice.

Each turn of the call is one webhook: Twilio turns the caller's speech into text
(`<Gather input="speech">`), we run the same worker turn as for any other channel, and
answer with TwiML that speaks the reply (`<Say>`) and listens again. No audio is recorded
or stored; the transcript of each turn is the conversation, like a text thread.

Signature checking is the same as SMS. A call reaches the business whose SMS number was
dialled (one Twilio number takes both texts and calls).
"""

from __future__ import annotations

import secrets
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from novaxis_core.channels.base import InboundRequest, NormalisedInbound, ParseError, ProviderRef
from novaxis_core.channels.twilio_sms import TwilioSmsAdapter


class TwilioVoiceAdapter(TwilioSmsAdapter):
    channel = "twilio_voice"

    def parse_inbound(self, request: InboundRequest) -> NormalisedInbound:
        f = request.form
        sid, sender, to = f.get("CallSid"), f.get("From"), f.get("To")
        if not sid or not sender or not to:
            raise ParseError("missing CallSid, From or To")
        speech = (f.get("SpeechResult") or "").strip()
        if not speech:
            raise ParseError("no speech in this turn")
        turn = request.query.get("t", "1")
        return NormalisedInbound(
            channel=self.channel,
            provider_ref=f"voice:{sid}:{turn}",
            tenant_ref=to,
            sender_phone=sender,
            body=speech,
            raw={"confidence": f.get("Confidence", "")},
        )

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        # The reply is spoken in the webhook's own answer (TwiML); there is nothing to send.
        return ProviderRef(provider_ref=f"voice:{to}:{secrets.token_urlsafe(8)}")


# --- TwiML ------------------------------------------------------------------------------


def _say(text: str, voice: str | None) -> str:
    attrs = ' language="en-GB"' + (f" voice={quoteattr(voice)}" if voice else "")
    return f"<Say{attrs}>{escape(text)}</Say>"


def listen(prompt: str, action: str, voice: str | None = None) -> str:
    """Speak `prompt` (the caller can talk over it) and send what they say to `action`."""
    return (
        "<Response>"
        f'<Gather input="speech" language="en-GB" speechTimeout="auto" method="POST" '
        f"action={quoteattr(action)}>{_say(prompt, voice)}</Gather>"
        f"{_say('Sorry, I did not hear anything. Goodbye.', voice)}<Hangup/>"
        "</Response>"
    )


def hold(action: str, voice: str | None = None) -> str:
    """The reply is not ready yet: say so, pause, and ask again."""
    return (
        f'<Response>{_say("One moment please.", voice)}<Pause length="2"/>'
        f'<Redirect method="POST">{escape(action)}</Redirect></Response>'
    )


def connect(text: str, number: str, voice: str | None = None) -> str:
    """Speak, then put the caller through to a person."""
    return f"<Response>{_say(text, voice)}<Dial>{escape(number)}</Dial></Response>"


def goodbye(text: str, voice: str | None = None) -> str:
    return f"<Response>{_say(text, voice)}<Hangup/></Response>"
