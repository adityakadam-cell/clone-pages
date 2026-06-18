"""
API-Agent — Flask app entry point.

A 7-agent wizard (separate page per agent, like the optimizer flow):
  Agent 1  Page URL input
  Agent 2  Design capture (CSS / JS from pasted HTML)
  Agent 3  Content intake (1-10 files .docx/.pdf/.csv/.txt OR a Google Sheet)
  Agent 4  Analysis (loading screen + requirements board)
  Agent 5  Recheck & sync (auto-build missing fields)
  Agent 7  Preview & approve
  Agent 6  Output & download (one-by-one or bulk ZIP)

Run order: 1 -> 2 -> 3 -> 4 -> 5 -> 7 -> 6
Local dev:  python app.py   ->  http://localhost:5000
Production: gunicorn wsgi:app   (see README.md)
"""
import logging
import os
import secrets
import threading

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash, send_from_directory,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import Config, init_dirs
from agents import (
    agent1_url_input as a1,
    agent2_design_capture as a2,
    agent3_content_intake as a3,
    agent4_analysis as a4,
    agent5_recheck_sync as a5,
    agent6_output as a6,
    agent7_preview_approve as a7,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("api-agent")

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
init_dirs()

# ----------------------------------------------------------------------
# Server-side per-session store (optimizer-wizard pattern).
# Pasted HTML + content blobs blow past the 4 KB Flask cookie limit, so we
# keep everything server-side and only put a small session id in the cookie.
# NOTE: process-local dict -> run with a single Gunicorn worker (see render.yaml).
# ----------------------------------------------------------------------
_store: dict = {}
_store_lock = threading.Lock()


def sdata() -> dict:
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_hex(16)
        session["sid"] = sid
    with _store_lock:
        return _store.setdefault(sid, {})


def clear_sdata():
    sid = session.pop("sid", None)
    if sid:
        with _store_lock:
            _store.pop(sid, None)


# Run order + page metadata for the progress nav.
FLOW = Config.AGENT_ORDER  # [1, 2, 3, 4, 5, 7, 6]
LABELS = {
    1: "URL", 2: "Design", 3: "Content",
    4: "Analyze", 5: "Sync", 7: "Approve", 6: "Download",
}


def _next(agent: int) -> int:
    i = FLOW.index(agent)
    return FLOW[i + 1] if i + 1 < len(FLOW) else agent


def _prev(agent: int) -> int:
    i = FLOW.index(agent)
    return FLOW[i - 1] if i > 0 else agent


@app.context_processor
def inject_nav():
    done = {k for k in sdata().keys() if k.startswith("agent")}
    return {"FLOW": FLOW, "LABELS": LABELS, "done_keys": done}


# ===================== Routes =====================
@app.route("/")
def home():
    clear_sdata()
    return redirect(url_for("agent", n=1))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.route("/restart")
def restart():
    clear_sdata()
    return redirect(url_for("agent", n=1))


@app.errorhandler(413)
def too_large(_):
    flash("Upload too large or too many files.", "error")
    return redirect(url_for("agent", n=3))


# ---- Generic GET for any agent page ----
@app.route("/agent/<int:n>")
def agent(n):
    if n not in FLOW:
        return redirect(url_for("agent", n=1))
    d = sdata()
    tpl = f"agent{n}.html"
    ctx = dict(n=n, nxt=_next(n), prv=_prev(n), data=d,
               max_files=Config.MAX_UPLOAD_FILES,
               allowed=sorted(Config.ALLOWED_EXTENSIONS))
    if n == 1:
        ctx["url"] = d.get("agent1", {}).get("url", "")
    if n == 6:
        ctx["built"] = d.get("built", [])
    return render_template(tpl, **ctx)


# ---- Agent 1: URL ----
@app.route("/agent/1", methods=["POST"])
def post_agent1():
    res = a1.run(request.form.get("url", ""))
    if not res["ok"]:
        flash(res["error"], "error")
        return redirect(url_for("agent", n=1))
    sdata()["agent1"] = res["data"]
    return redirect(url_for("agent", n=_next(1)))


# ---- Agent 2: Design ----
@app.route("/agent/2", methods=["POST"])
def post_agent2():
    res = a2.run(html=request.form.get("html", ""),
                 base_url=request.form.get("base_url", ""))
    if not res["ok"]:
        flash(res["error"], "error")
        return redirect(url_for("agent", n=2))
    sdata()["agent2"] = res["data"]
    flash(res["message"], "ok")
    return redirect(url_for("agent", n=_next(2)))


# ---- Agent 3: Content (files OR sheet) ----
@app.route("/agent/3", methods=["POST"])
def post_agent3():
    mode = request.form.get("mode", "files")
    if mode == "sheet":
        res = a3.run_sheet(request.form.get("sheet_url", ""),
                           api_key=Config.GOOGLE_API_KEY)
    else:
        res = a3.run_files(request.files.getlist("files"))
    if not res["ok"]:
        flash(res["error"], "error")
        return redirect(url_for("agent", n=3))
    sdata()["agent3"] = res["data"]
    flash(res["message"], "ok")
    return redirect(url_for("agent", n=_next(3)))


# ---- Agent 4: Analysis (called by the processing screen) ----
@app.route("/api/agent4/analyze", methods=["POST"])
def api_agent4():
    res = a4.run(sdata())
    sdata()["agent4"] = res["data"]
    return jsonify(res)


# ---- Agent 5: Sync ----
@app.route("/api/agent5/sync", methods=["POST"])
def api_agent5():
    res = a5.run(sdata())
    sdata()["agent5"] = res["data"]
    return jsonify(res)


# ---- Agent 7: Preview & approve ----
@app.route("/api/agent7/preview")
def api_agent7_preview():
    return jsonify(a7.preview(sdata()))


@app.route("/agent/7", methods=["POST"])
def post_agent7():
    ids = request.form.getlist("approved_ids")
    res = a7.approve(sdata(), ids)
    if not res["ok"] or res["data"]["count"] == 0:
        flash("Approve at least one page.", "error")
        return redirect(url_for("agent", n=7))
    sdata()["agent7"] = res["data"]
    # Build immediately, then go to the download page.
    build = a6.build(sdata())
    if not build["ok"]:
        flash(build["error"], "error")
        return redirect(url_for("agent", n=7))
    sdata()["built"] = build["data"]["built"]
    flash(build["message"], "ok")
    return redirect(url_for("agent", n=6))


# ---- Agent 6: Download ----
@app.route("/download/<path:filename>")
def download_one(filename):
    return send_from_directory(Config.OUTPUT_DIR, filename, as_attachment=True)


@app.route("/api/agent6/zip", methods=["POST"])
def api_agent6_zip():
    data = request.get_json(force=True)
    return jsonify(a6.zip_pages(data.get("filenames", [])))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n API-Agent dev server -> http://localhost:{port}\n")
    app.run(host=os.environ.get("FLASK_HOST", "127.0.0.1"), port=port, debug=False)
