# API-Agent — Project Flow Specification

**Stack constraint:** Python (backend) + HTML / CSS / JavaScript (frontend) **only**. No other language.
**Goal:** Clone product web pages so the design matches an existing page, fill them with content from a content doc / Google Sheet, verify completeness, and let the user download the finished pages individually or as a bulk ZIP.
**Deploy target:** GitHub → Render (public shareable URL).

---

## The 7-Agent Flow

### Agent 1 — Page URL Input
- This is the **URL-input step**: the user inserts the **Page URL** (the live/reference page to clone).
- This URL is the entry point of the whole flow.

### Agent 2 — Design Capture
- User provides the **HTML of the page**.
- Agent fetches the page's **CSS and JavaScript** from that HTML so the cloned pages match the design of the other (existing) pages.
- Output: a reusable design/template (layout + styles + scripts) to apply to every cloned page.

### Agent 3 — Content Intake (two input modes)
**Mode A — File upload**
- Allowed formats only: **.docx, .pdf, .csv, .txt**.
- **Minimum 1 file, maximum 10 files** per upload round.
- Multiple files can be uploaded in a single round.

**Mode B — Google Doc / Google Sheet**
- Read limited cells and fetch data from there.
- From the sheet, pull these fields per page:
  - **Product** → Page name
  - **Doc** → Content source (the actual page content is fetched from the `Doc` cell)
  - **Meta Title** → page meta title
  - **Meta Description** → page meta description
  - **Url (link)** → the page URL
- Field mapping summary:
  - Content ← `Doc`
  - Page URL ← `Url (link)`
  - Meta Title ← `Meta Title`
  - Meta Description ← `Meta Description`
  - Page name ← `Product`

### Agent 4 — Loading & Analysis
- Show a **loading screen** while everything is analyzed.
- Detect anything missing; if something is missing, post a **requirement on the board**.
- Provide a **Back button** to return/correct.

### Agent 5 — Recheck & Sync
- Recheck and **sync all content** from the doc and the page.
- If anything is still missing, **build that part automatically**, with the design matching the existing page design, and complete it.

### Agent 7 — Preview & Approve
- Before final hand-off, show a **preview** of each finished page.
- User reviews and **approves** (human approval gate). Only approved pages move forward.
- Sits between Agent 5 (recheck/sync) and the final download — it gates the Agent 6 output.

### Agent 6 — Output & Download
- After approval (Agent 7), provide all pages to **download one by one**.
- Also allow **bulk-select** and **download as a ZIP**.

> **Run order:** Agent 1 → 2 → 3 → 4 → 5 → **7 (Preview & Approve)** → 6 (Download).
> Agents are numbered per your spec; Preview & Approve (7) runs just before the final download.

---

## Confirmed Constraints
- Backend: **Python only** (e.g. Flask or FastAPI).
- Frontend: **HTML, CSS, JavaScript only**.
- Upload rules: 1–10 files; formats `.docx`, `.pdf`, `.csv`, `.txt`.
- All project files live in the connected **api-agent** folder.
