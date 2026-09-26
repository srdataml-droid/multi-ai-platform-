# ADR 0009: Sensitive fields are encrypted in the application, and a refused reply still says something

- Status: accepted
- Date: 2026-09-26
- Chunk: 6

## Context
Dental intake collects symptoms, pain, duration and funding status. Under UK GDPR these are
special category data; a leak into a log line or an analytics export is a breach. The pack
marks such questions `sensitive: true`; the platform must make that flag mean something.

## Decisions
1. **Application-level Fernet encryption**, not pgcrypto. The key comes from
   `NOVAXIS_SENSITIVE_FIELDS_KEY` and never reaches the database; a database dump contains
   `enc:v1:...` tokens. Outside `local` and `test`, a missing key is a startup error rather
   than a silent fallback. Rotation is a re-encrypt job (not built yet; the `v1` prefix makes
   it possible).
2. **Encrypt on write, decrypt in process.** The `extract_fields` executor encrypts the pack's
   sensitive keys. The worker turn decrypts them only to validate intake and build the prompt.
   The model has already seen the symptom in the customer's message; encryption protects the
   structured field at rest, not the conversation from the model.
3. **Reveal by role.** `reveal(fields, keys, role)` returns plaintext for owner, staff and
   operator, and `[redacted]` for viewer. The conversation read endpoint uses it, so the
   dashboard cannot forget to.
4. **Nothing sensitive in logs or audit rows.** Executor results carry field keys, never
   values; the LLM trace carries tool names and token counts. A log-capture test runs a dental
   turn and asserts the symptom text appears in no log record. `strip_for_analytics` replaces
   sensitive values with presence booleans for roll-ups (Chunk 9).
5. **Core finds the pack through a resolver.** `pack_registry.set_pack_resolver` is called
   when the packs package is imported, so core executors can ask which keys are sensitive
   without importing the packs package.
6. **A refused reply is not silence.** When the gate rejects the model's reply (safeguarding
   hit, opted-out contact, or a pack rule such as dental's clinical-advice detector), the turn
   sends the pack's fixed `handoff_notice` text and sets the conversation to `waiting_human`.
   The notice is a distinct action kind: never model-authored, exempt from the safeguarding
   rule because it is the safe response to it, still subject to opt-out.

## Consequences
- The dental pack's advice detector is a regex over the model's reply. It will catch common
  phrasings and miss creative ones; the system prompt does the primary work and the rule is
  the backstop. Evals (Chunk 13) measure both.
- `conversations.extracted` values for sensitive keys are opaque in SQL. Reports that need
  them must go through code with a staff-level role.
