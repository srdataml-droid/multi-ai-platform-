"""Speech to text for customers' voice notes, with Whisper (docs/voice-notes.md).

One adapter, like the open-model LLM adapter: any server with an OpenAI-compatible
`POST /audio/transcriptions` endpoint (multipart `file` + `model`). That covers a
self-hosted open-source Whisper (faster-whisper behind an OpenAI-compatible server), a
hosted open-weights Whisper (e.g. Groq), and OpenAI's own [VERIFY each provider's current
endpoint and model names]. Chosen with NOVAXIS_STT_PROVIDER:

- `none` (default): no transcription; the assistant asks the customer to type;
- `openai_compatible`: NOVAXIS_STT_BASE_URL, NOVAXIS_STT_API_KEY, NOVAXIS_STT_MODEL;
- `fake`: a fixed transcript (NOVAXIS_FAKE_TRANSCRIPT), for tests and demos.

The audio goes to whichever server is configured: with a hosted provider, that provider
processes customers' voices (docs/compliance.md).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from novaxis_core.settings import get_settings


class TranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Transcript:
    text: str
    model: str
    seconds: float


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, content_type: str, filename: str) -> Transcript: ...


class OpenAICompatSTT:
    RETRY_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        language: str = "",
        transport: httpx.BaseTransport | None = None,
        attempts: int = 3,
    ) -> None:
        if not base_url:
            raise ValueError("NOVAXIS_STT_BASE_URL is required for openai_compatible")
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._model = model
        self._language = language
        self._transport = transport
        self._attempts = attempts

    def transcribe(self, audio: bytes, content_type: str, filename: str) -> Transcript:
        data = {"model": self._model, "response_format": "json"}
        if self._language:
            data["language"] = self._language
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        started = time.monotonic()
        last: Exception | None = None
        with httpx.Client(transport=self._transport, timeout=30) as client:
            for attempt in range(self._attempts):
                try:
                    r = client.post(
                        f"{self._base}/audio/transcriptions",
                        headers=headers,
                        data=data,
                        files={"file": (filename, audio, content_type.split(";")[0])},
                    )
                except httpx.TransportError as exc:
                    last = exc
                else:
                    if r.status_code not in self.RETRY_STATUS:
                        if r.status_code >= 400:
                            raise TranscriptionError(f"speech-to-text answered {r.status_code}")
                        text = str(r.json().get("text", "")).strip()
                        return Transcript(text, self._model, time.monotonic() - started)
                    last = TranscriptionError(f"speech-to-text answered {r.status_code}")
                if attempt + 1 < self._attempts:
                    time.sleep(0.5 * (2**attempt))
        raise TranscriptionError(f"speech-to-text unavailable: {last}")


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[int, str]] = []

    def transcribe(self, audio: bytes, content_type: str, filename: str) -> Transcript:
        self.calls.append((len(audio), content_type))
        return Transcript(self.text, "fake", 0.0)


def build_stt() -> Transcriber | None:
    s = get_settings()
    if s.stt_provider == "none":
        return None
    if s.stt_provider == "openai_compatible":
        return OpenAICompatSTT(s.stt_base_url, s.stt_api_key, s.stt_model, s.stt_language)
    if s.stt_provider == "fake":
        return FakeSTT(s.fake_transcript)
    raise ValueError(f"unknown NOVAXIS_STT_PROVIDER {s.stt_provider!r}")
