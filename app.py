"""
API-Agent — Flask app entry point.

7-agent wizard. Run order: 1 -> 2 -> 3 -> 4 -> 5 -> 7 -> 8 -> 6
Session state persisted to a JSON file per browser (durable, no external deps).
Local dev: python app.py   |   Production: gunicorn app:app
"""
import json
import logging
import os
import secrets
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash, send_from_directory, g,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import Config, init_dirs
from core import registry
from agents import (
    agent1_url_input as a1,
    agent2_design_capture as a2,
    agent3_content_intake as a3,
    agent4_analysis as a4,
    agent5_recheck_sync as a5,
    agent6_output as a6,
    agent7_preview_approve as a7,
    agent8_verify as a8,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("api-agent")

BASE_DIR = Path(__file__).resolve().parent
SESS_DIR = BASE_DIR / ".sessions"
SESS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
init_dirs()


# ---------------------------------------------------------------------- #
# Durable per-browser store (JSON file on disk, keyed by a cookie sid).
# ---------------------------------------------------------------------- #
def _sid() -> str:
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_hex(16)
        session["sid"] = sid
    return sid


def _path(sid: str) -> Path:
    return SESS_DIR / f"{sid}.json"


def sdata() -> dict:
    if not hasattr(g, "store"):
        sid = _sid()
        p = _path(sid)
        try:
            g.store = json.loads(p.read_text("utf-8")) if p.exists() else {}
        except Exception:
            g.store = {}
    return g.store


def clear_sdata():
    sid = session.pop("sid", None)
    if sid:
        try:
            p = _path(sid)
            if p.exists():
                p.unlink()
        except Exception:
            pass
    if hasattr(g, "store"):
        delattr(g, "store")


@app.after_request
def _persist(resp):
    try:
        sid = session.get("sid")
        if sid and hasattr(g, "store"):
            _path(sid).write_text(json.dumps(g.store), "utf-8")
    except Exception as exc:  # pragma: no cover
        log.warning("session persist failed: %s", exc)
    return resp


FLOW = Config.AGENT_ORDER  # [1, 2, 3, 4, 5, 7, 8, 6]
LABELS = {2: "URL & Design", 3: "Content", 4: "Analyze",
          5: "Sync", 7: "Approve", 8: "Verify", 6: "Download"}


def _next(agent: int) -> int:
    i = FLOW.index(agent)
    return FLOW[i + 1] if i + 1 < len(FLOW) else agent


def _prev(agent: int) -> int:
    i = FLOW.index(agent)
    return FLOW[i - 1] if i > 0 else agent


@app.context_processor
def inject_nav():
    done = {k for k in sdata().keys() if str(k).startswith("agent")}
    return {"FLOW": FLOW, "LABELS": LABELS, "done_keys": done}


# ===================== Routes =====================
@app.route("/")
def home():
    clear_sdata()
    return redirect(url_for("agent", n=FLOW[0]))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.route("/docs-check")
def docs_check():
    """Verify the Google Docs service account is wired up.
    Visit this URL after setting GOOGLE_SERVICE_ACCOUNT_JSON."""
    from core.google_auth import is_configured, get_token, _account_info
    configured = is_configured()
    token = get_token() if configured else None
    email = ""
    try:
        info = _account_info() or {}
        email = info.get("client_email", "")
    except Exception:
        pass
    ok_all = configured and bool(token)
    return jsonify({
        "service_account_configured": configured,
        "token_obtained": bool(token),
        "client_email": email,
        "ready_to_read_docs": ok_all,
        "hint": ("All good — Docs will be read via the service account."
                 if ok_all else
                 "Set GOOGLE_SERVICE_ACCOUNT_JSON (Render env var = Secret File "
                 "path or raw JSON) and redeploy."),
    }), (200 if ok_all else 503)


@app.route("/ai-check")
def ai_check():
    """Confirm the Gemini AI builder is wired up. Visit after setting
    GEMINI_API_KEY (or GOOGLE_API_KEY with the Generative Language API enabled)."""
    from core import ai_writer
    from config import Config
    enabled = ai_writer.is_enabled()
    ok_call, detail = False, ""
    if enabled:
        try:
            plan = ai_writer.plan_page(
                "Test Product",
                [{"id": "specs", "heading": "Specifications", "kind": "text",
                  "furniture": False}],
                "## Specifications\nStandard: ASTM A312\nGrade: 304")
            ok_call = isinstance(plan, dict)
            detail = "model responded"
        except Exception as exc:
            detail = str(exc)[:300]
    return jsonify({
        "ai_enabled": enabled,
        "model": Config.AI_MODEL,
        "using_key": ("GEMINI_API_KEY" if Config.GEMINI_API_KEY
                      else ("GOOGLE_API_KEY" if Config.GOOGLE_API_KEY else "none")),
        "live_call_ok": ok_call,
        "detail": detail or ("set GEMINI_API_KEY and enable the Generative "
                             "Language API" if not enabled else ""),
    }), (200 if (enabled and ok_call) else 503)


@app.route("/restart")
def restart():
    clear_sdata()
    return redirect(url_for("agent", n=FLOW[0]))


@app.errorhandler(413)
def too_large(_):
    flash("Upload too large or too many files.", "error")
    return redirect(url_for("agent", n=3))


@app.route("/agent/<int:n>")
def agent(n):
    if n not in FLOW:
        return redirect(url_for("agent", n=FLOW[0]))
    d = sdata()
    ctx = dict(n=n, nxt=_next(n), prv=_prev(n), data=d,
               max_files=Config.MAX_UPLOAD_FILES,
               max_build=Config.MAX_BUILD_PAGES,
               allowed=sorted(Config.ALLOWED_EXTENSIONS))
    if n == 1:
        ctx["url"] = d.get("agent1", {}).get("url", "")
    if n == 6:
        ctx["built"] = d.get("built", [])
    return render_template(f"agent{n}.html", **ctx)


@app.route("/agent/2", methods=["POST"])
def post_agent2():
    # Step 1 now collects BOTH the page URL and the design HTML.
    url = request.form.get("url", "")
    res1 = a1.run(url)
    if not res1["ok"]:
        flash(res1["error"], "error")
        return redirect(url_for("agent", n=2))
    res = a2.run(html=request.form.get("html", ""), base_url=url)
    if not res["ok"]:
        flash(res["error"], "error")
        return redirect(url_for("agent", n=2))
    sdata()["agent1"] = res1["data"]
    sdata()["agent2"] = res["data"]
    flash(res["message"], "ok")
    return redirect(url_for("agent", n=_next(2)))


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
    # AI runs automatically once design + content are in: advance end-to-end.
    return _run_auto_pipeline()


@app.route("/api/agent4/analyze", methods=["POST"])
def api_agent4():
    res = a4.run(sdata())
    sdata()["agent4"] = res["data"]
    return jsonify(res)


@app.route("/api/agent5/sync", methods=["POST"])
def api_agent5():
    res = a5.run(sdata())
    sdata()["agent5"] = res["data"]
    return jsonify(res)


@app.route("/api/agent7/preview")
def api_agent7_preview():
    return jsonify(a7.preview(sdata()))


@app.route("/agent/7", methods=["POST"])
def post_agent7():
    ids = request.form.getlist("approved_ids")
    if len(ids) > Config.MAX_BUILD_PAGES:
        flash(f"You can build at most {Config.MAX_BUILD_PAGES} pages per round.", "error")
        return redirect(url_for("agent", n=7))
    res = a7.approve(sdata(), ids)
    if not res["ok"] or res["data"]["count"] == 0:
        flash(f"Approve at least one page (max {Config.MAX_BUILD_PAGES}).", "error")
        return redirect(url_for("agent", n=7))
    sdata()["agent7"] = res["data"]
    build = a6.build(sdata())
    if not build["ok"]:
        flash(build["error"], "error")
        return redirect(url_for("agent", n=7))
    sdata()["built"] = build["data"]["built"]
    registry.mark_built(build["data"]["built"])
    flash(build["message"], "ok")
    return redirect(url_for("agent", n=8))


@app.route("/api/agent8/verify", methods=["POST"])
def api_agent8():
    res = a8.run(sdata())
    sdata()["agent8"] = res["data"]
    return jsonify(res)


@app.route("/download/<path:filename>")
def download_one(filename):
    return send_from_directory(Config.OUTPUT_DIR, filename, as_attachment=True)


@app.route("/api/agent6/zip", methods=["POST"])
def api_agent6_zip():
    data = request.get_json(force=True)
    return jsonify(a6.zip_pages(data.get("filenames", [])))


def _run_auto_pipeline():
    """Run Analyze -> Sync -> Approve(next batch) -> Build(AI) -> Verify in one
    shot. Used both by the Auto-build button and automatically after content is
    loaded. The step stages stay visible; this advances them for you."""
    d = sdata()
    if "agent2" not in d or "agent3" not in d:
        flash("Add the design (Step 1) and content (Step 3) first.", "error")
        return redirect(url_for("agent", n=FLOW[0]))
    try:
        d["agent4"] = a4.run(d)["data"]
        d["agent5"] = a5.run(d)["data"]
        prev = a7.preview(d)["data"]
        ids = [it["id"] for it in prev.get("items", [])]
        if not ids:
            flash("Nothing left to build — every page is already done.", "ok")
            return redirect(url_for("agent", n=8))
        d["agent7"] = a7.approve(d, ids)["data"]
        build = a6.build(d)
        if not build["ok"]:
            flash(build["error"], "error")
            return redirect(url_for("agent", n=7))
        d["built"] = build["data"]["built"]
        registry.mark_built(build["data"]["built"])
        d["agent8"] = a8.run(d)["data"]
    except Exception as exc:  # pragma: no cover
        log.exception("auto-build failed")
        flash(f"Auto-build hit an error: {exc}", "error")
        return redirect(url_for("agent", n=4))
    flash(f"Auto-built {len(ids)} page(s) with AI. Review the verification "
          f"below, then download.", "ok")
    return redirect(url_for("agent", n=8))


@app.route("/auto", methods=["POST"])
def auto_build():
    return _run_auto_pipeline()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n API-Agent dev server -> http://localhost:{port}\n")
    app.run(host=os.environ.get("FLASK_HOST", "127.0.0.1"), port=port, debug=False)
