"""WhatsApp through Twilio: no Meta developer app, tokens or webhook review of our own.

Twilio posts WhatsApp messages to our webhook exactly like SMS (same signature, same form
fields), with numbers written `whatsapp:+447700900123`, and sends ours with the same API
(docs/whatsapp.md). For testing, Twilio's WhatsApp sandbox works in minutes; for real
customers the business's Twilio number is approved as a WhatsApp sender through Twilio.

A business is found by its WhatsApp number (`channels.twilio_whatsapp.config.number`) or,
if it has none, by its Twilio SMS number: one approved number then takes texts, calls
and WhatsApp. The same 24-hour reply rule as Meta's own API applies (outbound.py).
"""

from __future__ import annotations

from typing import Any

import httpx

from novaxis_core.channels.base import InboundRequest, NormalisedInbound, ProviderRef
from novaxis_core.channels.twilio_sms import TwilioSmsAdapter
from novaxis_core.settings import get_settings

PREFIX = "whatsapp:"


def plain_number(value: str) -> str:
    return value[len(PREFIX) :] if value.lower().startswith(PREFIX) else value


class TwilioWhatsAppAdapter(TwilioSmsAdapter):
    channel = "twilio_whatsapp"

    def parse_inbound(self, request: InboundRequest) -> NormalisedInbound:
        n = super().parse_inbound(request)
        return n.model_copy(
            update={
                "channel": self.channel,
                "tenant_ref": plain_number(n.tenant_ref),
                "sender_phone": plain_number(n.sender_phone or ""),
                "sender_name": request.form.get("ProfileName") or n.sender_name,
            }
        )

    def send(self, *, to: str, body: str, tenant_channel_config: dict[str, Any]) -> ProviderRef:
        s = get_settings()
        sender = str(
            tenant_channel_config.get("number") or ""
        )  # outbound.py fills in the SMS number
        if not sender:
            raise ValueError("tenant has no WhatsApp number configured")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
        with httpx.Client(transport=self._transport, timeout=10) as client:
            r = client.post(
                url,
                auth=(s.twilio_account_sid, s.twilio_auth_token),
                data={
                    "From": PREFIX + plain_number(sender),
                    "To": PREFIX + plain_number(to),
                    "Body": body,
                },
            )
        r.raise_for_status()
        return ProviderRef(provider_ref=str(r.json()["sid"]))
