# Voice notes (speech to text with Whisper)

When a customer sends a **voice note** (WhatsApp, or audio in an MMS or an email), the
platform fetches it, transcribes it with **Whisper**, and only then lets the assistant (or
the business's own agent) answer, using what was said.

```
voice note ──> stored like any attachment ──> Whisper ──> transcript on the message
                                                           │
             emergency check reads it ("I can smell gas" said out loud still escalates)
             the assistant / your agent reads it; staff see it under the audio
```

Code: adapter `packages/core/novaxis_core/stt.py`, the job `media.py` (`fetch_media`,
`text_of`), tests `apps/api/tests/test_voice_notes.py`.

## What happens

| Case | Result |
|---|---|
| Transcribed | The assistant sees `[Voice note]: <what was said>`; staff see the transcript under a "voice note" link to the audio |
| Emergency words in the voice note | The emergency check fires exactly as for text: escalation, honest emergency reply, no model involved (tested) |
| Speech to text not set up, or it failed | The assistant is told the note could not be heard and asks the customer to type; staff see why (tested) |
| The fetch-and-transcribe job fails for good | The conversation goes to a person and staff are alerted (the job carries the conversation id) |

The assistant's turn **waits** for the transcript: the job queues the turn when it is done.
A business's own agent is pushed `message.received` after that, so it reads the transcript
too (`/agent/v1/conversations/{id}` shows it in the message text).

## Choosing where Whisper runs

One setting picks any server with an OpenAI-compatible `POST /audio/transcriptions`
endpoint. Your options, open-source first:

| Option | What it is | Cost | Speed | Customer audio goes to |
|---|---|---|---|---|
| **A. Self-hosted open-source** | [Speaches](https://github.com/speaches-ai/speaches) (formerly faster-whisper-server): faster-whisper in Docker, OpenAI-compatible | Your server only | CPU: fine for short notes with a small model; GPU: fast | Your own server |
| **B. Groq (hosted open-weights Whisper)** | `whisper-large-v3-turbo` on Groq's hardware | about **$0.04 per hour of audio**, 10-second minimum per request [VERIFY] | Very fast (reported 200x real time) [VERIFY] | Groq (a sub-processor) |
| **C. OpenAI** | `whisper-1` or `gpt-4o-mini-transcribe` | **$0.006/min** (whisper-1) or **$0.003/min** (mini) [VERIFY] | Fast | OpenAI (a sub-processor) |

A typical voice note is 10 to 30 seconds. Even at 1,000 voice notes a month that is under a
dollar on Groq; hosting option A on a small always-on server costs more than that, but keeps
the audio in-house.

**Recommendation:** start with **B (Groq)** for the pilot: cheapest, fastest, no server to
run, and it is the open-weights Whisper model. Move to **A** when a business requires the
audio to stay on your own infrastructure, or when volume makes a server worthwhile.
Your laptop (Ryzen 7, no GPU) can run option A for testing with a small model.

## Turning it on (founder)

Set these on Vercel `novaxis-api` (Production), mark the key **sensitive**, then redeploy:

| Variable | A. Self-hosted (Speaches) | B. Groq | C. OpenAI |
|---|---|---|---|
| `NOVAXIS_STT_PROVIDER` | `openai_compatible` | `openai_compatible` | `openai_compatible` |
| `NOVAXIS_STT_BASE_URL` | `https://<your server>/v1` | `https://api.groq.com/openai/v1` [VERIFY] | `https://api.openai.com/v1` |
| `NOVAXIS_STT_API_KEY` | the key you set on the server (if any) | your Groq API key | your OpenAI API key |
| `NOVAXIS_STT_MODEL` | the model you loaded, e.g. `Systran/faster-whisper-small` [VERIFY] | `whisper-large-v3-turbo` | `whisper-1` or `gpt-4o-mini-transcribe` |
| `NOVAXIS_STT_LANGUAGE` | optional, e.g. `en`; empty = detect | same | same |

**Option A quick start** (on a VPS, Railway or your laptop), roughly [VERIFY the current
image name and flags in the Speaches README]:

```bash
docker run -p 8000:8000 ghcr.io/speaches-ai/speaches:latest-cpu
# then download a model through its API or UI, and point NOVAXIS_STT_BASE_URL at
# https://<host>/v1 (put it behind https; never expose it without a key or firewall)
```

**Check it works:** send a WhatsApp voice note to a business's number and open the
conversation: the transcript appears under "voice note". Or set `NOVAXIS_STT_PROVIDER=fake`
locally to see the flow without any server.

## Limits and privacy

- Audio is stored like photos (same retention and erasure) and counts toward the 10 MB
  attachment limit; longer recordings are refused and the customer is asked to type.
- Transcription quality depends on the model and on accents and noise; staff can always
  play the original.
- With a hosted provider (B or C), customers' voices are processed by that provider: add
  it to your sub-processor list and check its data-processing terms and where it processes
  data [VERIFY each provider's DPA and retention]. Option A keeps audio on your server.
- Not transcribed: phone calls (Twilio already turns speech into text, docs/voice.md) and
  the website chat's microphone (the browser does it).
