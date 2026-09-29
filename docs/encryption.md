# Encryption at rest

What is encrypted before it reaches the database, with one key (Fernet, `enc:v1:` prefix):

| Data | Where |
|---|---|
| Every message's text, both ways (what customers write, the assistant's and staff replies) | `messages.body` |
| Voice-note transcripts | `messages.media[].transcript` |
| Conversation summaries | `conversations.summary` |
| Private answers (the trade's sensitive questions, and questions a business marks private) | `conversations.extracted` |
| Calendar credentials, agent webhook secrets | `integrations`, `agent_keys` |

The application decrypts on read, so staff and the assistant see plain text; a database
dump, a backup or anyone with SQL access sees ciphertext. Migration 0022 encrypted what was
stored before. Viewers still see private answers as `[redacted]`.

Not encrypted (needed for matching and routing): contact names, phone numbers and email
addresses, and the text of proposals shown in Approvals (a reply draft, a held-back claim).

## The key

`NOVAXIS_SENSITIVE_FIELDS_KEY` in the Vercel project `novaxis-api`, stored as a sensitive
variable, so **nobody can read it back, including you**. If it is lost (the variable
deleted or overwritten, the project recreated), every message becomes unreadable. So keep
your own copy: change to a key you have saved, once, before real customers.

## Changing to a key you have saved (about 10 minutes)

1. On your laptop, make a key and save it in your password manager:
   `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Vercel → novaxis-api → Settings → Environment Variables → add
   `NOVAXIS_SENSITIVE_FIELDS_KEY_NEXT` = that key (sensitive, production and preview).
   Redeploy. New data is now encrypted with your key; the old key still reads the rest.
3. Move the stored data over: call `POST /internal/rekey` with the cron secret until it
   answers `"remaining": 0` (each call rewrites up to 2,000 rows). Novaxis can run this for
   you from the database console.
4. Replace `NOVAXIS_SENSITIVE_FIELDS_KEY` with your key, delete `..._NEXT`, redeploy.

Several keys can also be given comma separated in `NOVAXIS_SENSITIVE_FIELDS_KEY`: the first
encrypts, any of them decrypts.
