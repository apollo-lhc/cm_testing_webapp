# visualizations.py
"""
Defines routes and logic for visualizing Eyescan data in the Flask web application.
Routes:
- /viz: Main visualization menu for selecting serial numbers and dates.
- /viz/<serial>/date/<date>: Page to view Eyescan data for a specific serial and date.
- /viz/api/<serial>/date/<date>: API endpoint returning JSON data for Eyescan artifacts.
- /viz/file/<serial>/<date>/<filename>: Endpoint to serve individual Eyescan files.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, send_from_directory, abort, jsonify

from constants import APOLLO_ROOT, DATE_RE, ALLOWED_EXTS
from utils import _safe_under, _list_serial_dirs, _list_dates, _list_date_files, _group_eyescan_artifacts

visualizations_bp = Blueprint("visualizations", __name__)


@visualizations_bp.route("/eyescan")
def eyescan_home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    serials = _list_serial_dirs()
    selected_serial = (request.args.get("serial") or "").strip()
    dates = _list_dates(selected_serial) if selected_serial else []

    return render_template(
        "viz/eyescan_menu.html",
        serials=serials,
        selected_serial=selected_serial,
        dates=dates,
    )

@visualizations_bp.route("/eyescan/<serial>/date/<date>")
def eyescan_date(serial: str, date: str):
    if "user_id" not in session:
        return redirect(url_for("login"))

    # validate existence via safe resolve
    try:
        _ = _safe_under(APOLLO_ROOT, f"{serial}/scans/{date}")
    except ValueError:
        abort(400)

    if not DATE_RE.match(date):
        abort(400)

    # Used by template JS to fetch JSON
    return render_template(
        "viz/eyescan_date.html",
        serial=serial,
        date=date,
    )

@visualizations_bp.route("/eyescan/api/<serial>/date/<date>")
def eyescan_date_api(serial: str, date: str):
    if "user_id" not in session:
        return abort(401)

    if not DATE_RE.match(date):
        abort(400)

    files = _list_date_files(serial, date)
    cards = _group_eyescan_artifacts(files)

    # Build URLs
    def file_url(fname: str) -> str:
        return url_for("visualizations.viz_file", serial=serial, date=date, filename=fname)

    payload = []
    for c in cards:
        payload.append({
            "label": c["label"],
            "png": file_url(c["png"]) if c["png"] else None,
            "pdf": file_url(c["pdf"]) if c["pdf"] else None,
            "csv": file_url(c["csv"]) if c["csv"] else None,
        })

    return jsonify({
        "serial": serial,
        "date": date,
        "count": len(payload),
        "items": payload,
    })

@visualizations_bp.route("/eyescan/file/<serial>/<date>/<path:filename>")
def eyescan_file(serial: str, date: str, filename: str):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if ".." in filename or filename.startswith(("/", "\\")):
        abort(400)

    if not DATE_RE.match(date):
        abort(400)

    # resolve + serve
    try:
        abs_dir = _safe_under(APOLLO_ROOT, f"{serial}/scans/{date}")
    except ValueError:
        abort(400)

    abs_path = (abs_dir / filename).resolve()
    if abs_dir not in abs_path.parents:
        abort(400)

    if not abs_path.exists() or not abs_path.is_file():
        abort(404)

    if abs_path.suffix.lower() not in ALLOWED_EXTS:
        abort(403)

    return send_from_directory(str(abs_dir), filename, as_attachment=False)
