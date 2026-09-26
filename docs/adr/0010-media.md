# ADR 0010: Customer media lives in object storage under the tenant's prefix

- Status: accepted
- Date: 2026-09-26
- Chunk: 7

## Context
Restoration customers send photos of damage; email brings attachments. Provider URLs expire
and need provider credentials, and a webhook must answer fast.

## Decisions
1. **One `BlobStore` interface, two implementations.** `LocalBlobStore` writes under a
   directory for development and tests. `SupabaseBlobStore` uses the Storage REST API with the
   service key; the bucket is private and reads go through short-lived signed URLs. Field
   names were written from the API's documented shape and must be checked on first deploy
   `[VERIFY]`.
2. **Keys are `<tenant_id>/<message_id>/<n>.<ext>`.** A tenant's media can be listed, exported
   or purged by prefix, which Chunk 12's retention and export jobs will rely on.
3. **Inline now, URL later.** Postmark hands attachment bytes inline; they are stored during
   the request. Twilio hands a URL that needs account auth; a `fetch_media` job downloads it,
   so the webhook returns without waiting on Twilio. Either way the message's `media` entry
   gains `stored_key`, `size`, `content_type`, or `error`. `messages` stays append-only apart
   from a column-level grant on `media` (migration 0005).
4. **Limits.** 10 MB per object; images, PDF and MP4 only. Anything else is recorded as an
   error on the entry and the message still reaches the worker.
5. **Access.** Never public. The local store is served by `GET /media/{key}` to staff-level
   roles of the owning tenant only; a viewer gets 403, another tenant 404. The API never
   returns a provider URL.
6. **No image analysis in Phase 1.** The dashboard shows thumbnails; the technician looks.
7. **Virus scanning deferred.** Files are stored as opaque bytes, never executed, served with
   their declared type to staff who chose to open them. The residual risk is a malicious
   image or PDF opened on a staff machine. Revisit with a scanning step before any tenant
   whose staff open attachments on managed devices with strict policies.

## Consequences
- The restoration pack asks for photos in its prompt but never blocks intake on them.
- Retention (Chunk 12) must purge storage by prefix as well as rows.
