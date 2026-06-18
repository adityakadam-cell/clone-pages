# API-Agent

A 7-agent pipeline that **clones a web page's design** and fills it with content
from uploaded documents or a Google Sheet, then lets you **preview, approve and
download** the finished pages — individually or as a ZIP.

> **Stack:** Python (Flask) + HTML / CSS / JavaScript only. No other language.

---

## The 7 agents

| # | Agent | What it does |
|---|-------|--------------|
| 1 | **URL input** | Insert the reference page URL to clone. |
| 2 | **Design capture** | Paste page HTML; extracts CSS & JS so clones match the design. |
| 3 | **Content intake** | Upload 1–10 files (`.docx`, `.pdf`, `.csv`, `.txt`) **or** read a Google Sheet (Product, Doc, Meta Title, Meta Description, Url (link)). |
| 4 | **Analysis** | Loading screen + gap analysis; raises a requirements board. |
| 5 | **Recheck & sync** | Auto-builds any missing field so each page is complete & on-design. |
| 7 | **Preview & approve** | Review each page; approve the ones to ship. |
| 6 | **Output & download** | Build pages; download one-by-one or bulk ZIP. |

> Run order: **1 → 2 → 3 → 4 → 5 → 7 → 6** (approval gates the final download).

---

## Project structure

```
api-agent/
├── app.py                 # Flask entry point + routes
├── config.py              # Settings, upload rules, agent order
├── requirements.txt
├── render.yaml            # Render deploy blueprint
├── Procfile               # gunicorn start command
├── runtime.txt            # Python version
├── .env.example           # Copy to .env
├── .gitignore
├── agents/                # The 7 agents
│   ├── agent1_url_input.py
│   ├── agent2_design_capture.py
│   ├── agent3_content_intake.py
│   ├── agent4_analysis.py
│   ├── agent5_recheck_sync.py
│   ├── agent6_output.py
│   └── agent7_preview_approve.py
├── core/                  # Pipeline + helpers
│   ├── pipeline.py        # session state between agents
│   ├── utils.py           # responses, validation, file parsing
│   └── sheet_reader.py    # Google Sheet -> mapped rows
├── wsgi.py                # Gunicorn entry point
├── templates/             # One page per agent (optimizer-style flow)
│   ├── base.html          # Shared layout + agent progress nav
│   ├── agent1.html        # URL input
│   ├── agent2.html        # Design capture
│   ├── agent3.html        # Content intake (files / sheet)
│   ├── agent4.html        # Analysis (processing screen)
│   ├── agent5.html        # Recheck & sync
│   ├── agent7.html        # Preview & approve
│   └── agent6.html        # Download
├── static/css/style.css
├── uploads/               # user uploads (gitignored)
└── output/                # generated pages + zips (gitignored)
```

---

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then edit SECRET_KEY
python app.py                    # http://localhost:5000
```

---

## Deploy to Render

1. Push this folder to a GitHub repo.
2. In Render: **New → Blueprint**, point it at the repo (uses `render.yaml`).
   Or **New → Web Service** with:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
3. Set the `SECRET_KEY` env var (Render can auto-generate it).
4. Deploy — you get a public `https://<name>.onrender.com` URL to share.

---

## Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: API-Agent 7-agent page cloner"
git branch -M main
git remote add origin https://github.com/<you>/api-agent.git
git push -u origin main
```
