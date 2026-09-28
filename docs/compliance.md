# Compliance controls

Each control the platform enforces, and the test that proves it. A control without a test is
listed as open. This is an engineering checklist, not legal advice: every business using the
platform is the controller of its customers' data and needs its own adviser's sign-off
[VERIFY with a UK data-protection adviser before the first real business].

## In place

| Control | How | Test |
|---|---|---|
| One business can never read, change or add another's rows | Postgres RLS on every tenant table, forced, one policy | `packages/db/tests/test_rls.py` (all), `test_every_tenant_table_has_forced_rls_and_a_policy` |
| Platform-only tables are closed to the app | Forced RLS, no policy, no grant | `test_service_only_tables_are_closed_to_the_app_role` |
| The conversation record cannot be rewritten | App role has no UPDATE or DELETE on messages; audit log is insert-only | `test_messages_cannot_be_updated`, `test_messages_cannot_be_deleted`, `test_audit_record_writes_and_is_immutable` |
| Health details are encrypted at rest and shown by role | Fernet on the pack's sensitive intake keys | `packages/core/tests/test_sensitive.py` (all) |
| An SMS or email "STOP" is honoured on that channel | Consent flips to opted-out, confirmation sent, nothing more sent | `test_stop_flips_consent_sends_confirmation_and_creates_no_job`, `test_send_refuses_opted_out_contact`, `test_opted_out_contact_is_not_answered_until_start` |
| "Cancel" with a booking cancels the booking, not the customer | Opt-out words per channel | `test_cancel_by_text_cancels_the_booking_not_the_customer`, `test_stop_on_web_chat_is_just_a_message`, eval `hvac/06_cancel_on_chat_is_not_an_opt_out` |
| Callers hear that they are talking to an AI before anything else; call audio is never recorded (only the text of each turn is kept) | Disclosure is the call greeting; speech-to-text returns text only | `test_a_call_is_greeted_with_the_ai_disclosure_and_listens` |
| Customers are told they are talking to an AI, and where the privacy notice is | Disclosure and `privacy_url` in the first reply | `test_disclosure_only_on_first_reply`, `test_first_reply_links_the_business_privacy_notice` |
| Access request: everything held about one customer, nothing about anyone else | `GET /contacts/{id}/export`, owners only, audited | `test_export_holds_everything_for_one_customer_and_nothing_for_another`, `test_only_owners_export_or_erase_and_never_with_a_booking_to_come` |
| Erasure: one customer and everything that names them, including photos | `POST /contacts/{id}/erase`, owners only, typed confirmation, refused while a booking is still to come | `test_erasure_removes_one_customer_everywhere_and_touches_no_one_else`, `test_only_owners_export_or_erase_and_never_with_a_booking_to_come` |
| Retention: customers with no activity for `retention_days` are erased | Daily `retention_purge` job per business | `test_purge_takes_only_customers_past_retention_and_only_in_that_business`, `test_the_purge_is_queued_once_a_day_per_business` |
| An SMS or email reaches only the business that owns the number or address | Unique database indexes on each SMS number and inbound address; exact-match routing that refuses ambiguity; owners cannot rewrite either after set-up | `test_a_second_business_can_never_hold_the_same_number_or_address`, `test_routing_matches_an_address_exactly_never_as_a_pattern`, `test_a_new_business_cannot_take_another_business_number_or_address`, `test_routing_addresses_are_stored_in_one_form` |
| Voice notes are heard by the emergency check; an untranscribed note is never guessed at; a failed transcription job hands the conversation to a person; audio follows the same retention and erasure as photos. Hosted speech to text is a sub-processor [VERIFY DPA] | media.py `text_of`, stt.py | `test_voice_notes.py` (all) |
| Pushes to an agent carry ids only, are signed and time-stamped, go only to public https addresses, and a customer whose push cannot be delivered goes to a person | agent_webhooks.py | `test_agent_webhooks.py` (all) |
| A business's own agent (agent API) proposes only; the gate, disclosure, emergency check and approvals stay with the platform; one business per key; no phone numbers or emails shared; keys hashed and revocable | agent.py, routes_agent.py, `assistant: external` | `test_agent_api.py` (all 9) |
| Approval model: advice only, approves nothing; learns from no message text or personal data; its failure never blocks the queue; a synthetic model is never shown to a real business | Prediction stored beside the proposal, state untouched; features are counts, flags and categories | `test_a_waiting_proposal_carries_the_models_guess_and_staff_see_it`, `test_features_carry_no_message_text`, `test_a_failing_model_never_stops_a_proposal_reaching_staff`, `test_a_real_business_never_sees_the_synthetic_model` |
| WhatsApp: only Meta can post messages; outside 24 hours only an approved template is used, with the message whole, otherwise nothing is sent and a person follows up | Signature over the raw body; 24-hour check before every send; template never cuts a message | `test_signed_messages_are_ingested_once_and_receipts_or_strangers_are_ignored`, `test_replies_go_out_within_24_hours_and_later_ones_go_to_a_person`, `test_after_24_hours_the_message_goes_whole_inside_the_approved_template`, `test_a_message_too_long_for_the_template_goes_to_a_person_not_cut_short`, `test_a_queued_message_outside_24_hours_goes_to_a_person_at_once_not_retried` |
| Webhook replays do nothing | Provider reference is unique per message | `test_replayed_webhook_is_a_noop` |
| Public endpoints are rate limited; the widget can be restricted to the business's own websites | Postgres counters shared by every instance; `widget_origins` | `test_login_attempts_are_limited`, `test_chat_messages_are_limited_per_visitor`, `test_a_business_can_restrict_which_websites_host_its_widget` |
| Security headers | CSP and frame blocking on the dashboard, nosniff and frame blocking on the API | `test_api_responses_carry_security_headers` |
| Risky actions wait for a person; safeguarding stops the assistant | One pure approval gate, table-tested | `packages/core/tests/test_gate.py::test_gate_table` |

## What erasure keeps

The audit log is insert-only and is not erased. Its rows hold event names, ids, times and
counts. A cancellation reason typed by a customer (first 200 characters) is the one place
customer words can appear [VERIFY whether that is acceptable, or redact it on erasure].
Daily metrics are counts with no personal data. Anything already copied into the business's
own booking software or calendar is outside the platform and must be deleted there.

## Open

| Control | Why open | Owner |
|---|---|---|
| Privacy notice and terms for Novaxis itself | Legal text; needs an adviser | Founder |
| ICO registration (data protection fee) | Paid registration | Founder |
| DPIA for dental (special category data) | Needs an adviser | Founder, before the first dental business |
| Processor agreement records (Twilio, Postmark, Anthropic, Supabase, Vercel) and regulated-data mode | Build plan Chunk 12, second half; needs the chosen vendors first | Founder chooses vendors, then build |
| Retention of the audit log itself | Needs a policy decision | Founder with adviser |
| Consent history (a ledger of each change) | Today only the current consent state is stored, with its source and time | Build when a business needs it |
