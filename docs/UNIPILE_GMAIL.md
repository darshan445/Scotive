# Unipile mailbox connect (Gmail + Outlook)

Scotive connects **Gmail** and **Outlook / Microsoft 365** through [Unipile](https://developer.unipile.com/) Hosted Auth. Unipile holds the verified Google/Microsoft apps; we store their `account_id` and call their Email API.

## Env

Same as before: `UNIPILE_DSN`, `UNIPILE_API_KEY`, `PUBLIC_API_URL`, `UNIPILE_WEBHOOK_SECRET`.

## Connect flow

1. Frontend opens confirm modal → `GET /api/gmail/oauth/start?provider=google|outlook`
2. Backend creates Hosted Auth link with `providers: ["GOOGLE"]` or `["OUTLOOK"]`
3. Unipile `notify_url` → upsert `gmail_connections` with `provider` + `unipile_account_id`
4. Mail list/get/send reuse `gmail_client.py` (Unipile Email API)

One mailbox per user. Connecting the other provider replaces the previous Unipile account.

## Webhooks

Unchanged — notify + account_status (auto-registered). No dashboard setup required.
