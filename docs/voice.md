# Voice

Customers can talk to the assistant in two ways. Both feed the same assistant as text:
the same packs, the approval step, the emergency pre-check, bookings and hand-offs.

| | Talking in the website chat | Phone calls |
|---|---|---|
| How | Mic and speaker buttons in the chat widget | Customer rings the business's Twilio number |
| Speech to text | The visitor's browser (Web Speech API) | Twilio (`<Gather input="speech">`) |
| Text to speech | The visitor's browser | Twilio (`<Say>`) |
| Cost | Free | Twilio number, call minutes and speech recognition [VERIFY current prices] |
| Audio stored | Never reaches us, only the text | Not recorded; the transcript of each turn is kept like a text thread |
| Works today | Yes, in Chrome, Edge and Safari; buttons hidden where unsupported | When a Twilio number and keys are set |

## Phone calls

```
caller rings  → POST /inbound/twilio/voice       greeting = the AI disclosure, then listen
caller speaks → POST /inbound/twilio/voice/turn  the worker turn runs now; the reply is spoken
reply slow    → POST /inbound/twilio/voice/wait  "one moment", check again (up to 4 times)
```

- **Emergency:** the pack's emergency pre-check fires as for text. If the business has an
  on-call phone number, the caller hears the emergency reply and is **put straight through**
  (`<Dial>`). Otherwise the call ends with the honest emergency reply (staff are alerted as
  for any emergency).
- **Hand-off:** if the assistant hands over (safeguarding, out of scope, a person needed),
  the caller is told the team has the message and the call ends; staff are alerted.
- **Slow reply:** after 8 seconds the caller hears "one moment please". After about 40 seconds
  the message goes to a person and the caller is told so. Nobody is left on a dead line.
- **Identity:** callers are matched by phone number, so a customer who texts and calls is
  one contact. Only Twilio can reach these webhooks (signature checked, as for SMS). A wait
  link only works for the caller whose conversation it is.
- **Replay:** Twilio sending the same turn twice does not run it twice.
- **Routing:** a call reaches the business whose SMS number was dialled (one number takes
  both). The number is unique per business (migration 0013).

### Turning it on (founder)

1. Twilio: buy a UK number with voice and SMS [VERIFY cost]. In the number's settings set
   **"A call comes in"** to webhook `https://novaxis-api.vercel.app/inbound/twilio/voice`
   (HTTP POST), and **"A message comes in"** to `.../inbound/twilio/sms`.
2. Vercel `novaxis-api`: set `NOVAXIS_TWILIO_ACCOUNT_SID` and `NOVAXIS_TWILIO_AUTH_TOKEN`
   (sensitive).
3. The business: the number is set in onboarding. In **Settings → Channels**, tick
   **"Answer phone calls to your SMS number with the assistant"**, and make sure an on-call
   contact has a phone number (Setup).
4. Ring the number.

Optional: a Twilio voice name in the business settings
`channels.twilio_voice.config.voice` (for example a British neural voice [VERIFY names]).
Without one, Twilio's default British English voice is used.

### Limits

- Twilio waits a limited time for each webhook answer (about 15 seconds [VERIFY]), and the
  reply must be ready by then or the caller hears "one moment". Fine with a fast hosted model;
  a slow model on a laptop will mean frequent waits.
- Speech is recognised turn by turn, so it feels like a polite walkie-talkie rather than a
  fluid conversation. The caller can talk over the assistant (barge-in within `<Gather>`).

## Open-source voice (later)

The founder prefers open-source models. For speech that means Whisper (speech to text) and an
open text-to-speech model, running on our own server and streaming audio both ways (Twilio
Media Streams over a WebSocket). That needs an **always-on service**: Vercel functions answer
one request at a time and cannot hold a live audio stream. It also gives a more natural,
interruptible conversation.

Plan, when volume or cost justifies it:
1. a small always-on service (Railway, Render or a VPS) for the audio stream;
2. streaming Whisper and the TTS model there (a GPU makes it fast enough);
3. the same worker turn, called from that service.

The webhook version above stays as the fallback.
