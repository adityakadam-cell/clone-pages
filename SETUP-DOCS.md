# Reading Google Docs — one-time service-account setup

The Google **Docs API rejects API keys** (you saw the `401 Unauthorized`). To read
Doc content (and isolate the **Final** tab), the app needs a **service account**.
This is a 5-minute, one-time setup. Your Docs are already "anyone with the link,"
so the service account can read them without sharing each one.

---

## 1. Create the service account (Google Cloud Console)

Use the **same project** as your API key (`My Project 54659`).

1. Go to **APIs & Services → Credentials**.
2. **Create credentials → Service account**.
3. Name it e.g. `api-agent-docs` → **Create and continue** → **Done** (no roles needed).
4. Open the new service account → **Keys** tab → **Add key → Create new key → JSON**.
5. A `.json` file downloads. Keep it safe — this is the credential.

Make sure the **Google Docs API** is **Enabled** (APIs & Services → Enabled APIs).
(It already is for you.)

> You do **not** need to share each Doc with the service account, because your
> Docs are shared "anyone with the link can view." (If you ever make a Doc
> private, share it with the service account's `client_email` instead.)

---

## 2. Give the key to Render

**Option A — Secret File (recommended; cleanest for the multi-line JSON):**

1. Render dashboard → your service → **Environment** → **Secret Files** → **Add Secret File**.
   - **Filename:** `service-account.json`
   - **Contents:** paste the entire downloaded JSON → **Save**.
   - Render mounts it at `/etc/secrets/service-account.json`.
2. **Environment Variables** → add:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = `/etc/secrets/service-account.json`
3. **Save changes** — Render redeploys.

**Option B — paste the raw JSON** as the value of `GOOGLE_SERVICE_ACCOUNT_JSON`
(works too, but the JSON is long and multi-line).

---

## 3. Verify it worked

Open this URL in your browser:

```
https://api-agent-gkxl.onrender.com/docs-check
```

- `"ready_to_read_docs": true` → ✅ done. Re-run the sheet; Docs will read the Final tab.
- `"service_account_configured": false` → the env var isn't set / didn't redeploy.
- `"token_obtained": false` → the JSON is invalid or truncated — re-paste it.

The response also shows the service account's `client_email`.

---

## 4. Local development

Put the JSON file in the project folder and add to `.env`:

```
GOOGLE_SERVICE_ACCOUNT_JSON=./service-account.json
```

The file is gitignored (`service-account*.json`) so it is never committed.

---

## What changes after this

- Agent 3's banner: `fetched content for 5 page(s)` (no 401).
- Each page contains only its **Final** tab content (Claude / Regenerate / SS excluded).
- Agent 8 turns green.
