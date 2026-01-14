# visualizations.py
"""
Defines routes and logic for visualizing Eyescan data in the Flask web application.
Routes:
- /eyescan: Main visualization menu for selecting serial numbers and dates.
- /eyescan/<serial>/date/<date>: Page to view Eyescan data for a specific serial and date.
- /eyescan/api/<serial>/date/<date>: API endpoint returning JSON data for Eyescan artifacts.
- /eyescan/file/<serial>/<date>/<filename>: Endpoint to serve individual Eyescan files.
"""

from sqlalchemy import desc
from flask import Blueprint, render_template, request, redirect, url_for, session, send_from_directory, abort, jsonify

from constants import APOLLO_ROOT, DATE_RE, ALLOWED_EXTS
from models import TestEntry
from utils import _safe_under, _list_serial_dirs, _list_dates, _list_date_files, _group_eyescan_artifacts, _entry_serial, _entry_fpga_temps, _summarize

visualizations_bp = Blueprint("visualizations", __name__)

@visualizations_bp.route("/")
def vis_home():
    """
    Visualizations landing page (mounted at /vis/).
    """
    if "user_id" not in session:
        return redirect(url_for("login"))

    viz_tiles = [
        {
            "title": "Eyescan Browser",
            "description": "Browse eyescans by CM serial and scan date.",
            "href": url_for("visualizations.eyescan_home"),
            "icon": "bi-graph-up",
        },
        {
            "title": "FPGA Temperatures",
            "description": "View FPGA temps across boards and drill into an individual test.",
            "href": url_for("visualizations.fpga_temp_home"),
            "icon": "bi-thermometer-half",
        },
    ]

    return render_template("vis/vis_home.html", viz_tiles=viz_tiles)

@visualizations_bp.route("/eyescan")
def eyescan_home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    serials = _list_serial_dirs()
    selected_serial = (request.args.get("serial") or "").strip()
    dates = _list_dates(selected_serial) if selected_serial else []

    return render_template(
        "vis/eyescan_menu.html",
        serials=serials,
        selected_serial=selected_serial,
        dates=dates,
    )


@visualizations_bp.route("/eyescan/<serial>/date/<date>")
def eyescan_date(serial: str, date: str):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if not DATE_RE.match(date):
        abort(400)

    # validate existence via safe resolve
    try:
        _ = _safe_under(APOLLO_ROOT, f"{serial}/scans/{date}")
    except ValueError:
        abort(400)

    return render_template(
        "vis/eyescan_date.html",
        serial=serial,
        date=date,
    )


@visualizations_bp.route("/eyescan/api/<serial>/date/<date>")
def eyescan_date_api(serial: str, date: str):
    if "user_id" not in session:
        abort(401)

    if not DATE_RE.match(date):
        abort(400)

    files = _list_date_files(serial, date)
    cards = _group_eyescan_artifacts(files)

    # Build URLs
    def file_url(fname: str) -> str:
        return url_for(
            "visualizations.eyescan_file",
            serial=serial,
            date=date,
            filename=fname,
        )

    payload = []
    for c in cards:
        payload.append({
            "label": c["label"],
            "png": file_url(c["png"]) if c.get("png") else None,
            "pdf": file_url(c["pdf"]) if c.get("pdf") else None,
            "csv": file_url(c["csv"]) if c.get("csv") else None,
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


# ================== FPGA TEMP VISUALIZATIONS  ==================

@visualizations_bp.route("/fpga-temp")
def fpga_temp_home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("vis/fpga_temp_menu.html")


@visualizations_bp.route("/fpga-temp/test/<int:entry_id>")
def fpga_temp_test(entry_id: int):
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("vis/fpga_temp_test.html", entry_id=entry_id)


@visualizations_bp.route("/fpga-temp/api/all")
def fpga_temp_api_all():
    """
    Returns:
    - latest_per_board: one representative (most recent) test per serial with any temp data
    - tests: listing of all recent tests with any temp data
    """
    if "user_id" not in session:
        abort(401)

    # Tune this if needed. 5000 is usually plenty for dashboards.
    entries = (
        TestEntry.query
        .order_by(desc(TestEntry.timestamp))
        .limit(5000)
        .all()
    )

    tests = []
    latest_per_board = {}  # serial -> summary row

    for e in entries:
        serial = _entry_serial(e)
        if not serial:
            continue

        fpga1, fpga2 = _entry_fpga_temps(e)
        if not fpga1 and not fpga2:
            continue

        s1 = _summarize(fpga1)
        s2 = _summarize(fpga2)

        row = {
            "entry_id": e.id,
            "serial": serial,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "fpga1_n": s1["n"],
            "fpga1_max": s1["max"],
            "fpga1_avg": s1["avg"],
            "fpga2_n": s2["n"],
            "fpga2_max": s2["max"],
            "fpga2_avg": s2["avg"],
            "detail_url": url_for("visualizations.fpga_temp_test", entry_id=e.id),
            "serial_url": url_for("visualizations.fpga_temp_serial", serial=serial),
        }
        tests.append(row)

        # first time we see a serial (we're iterating in desc timestamp order) => latest
        if serial not in latest_per_board:
            latest_per_board[serial] = row

    latest_list = list(latest_per_board.values())
    # stable sort by serial (nice for x-axis)
    latest_list.sort(key=lambda r: str(r["serial"]).lower())

    return jsonify({
        "latest_per_board": latest_list,
        "tests": tests,
        "count_latest": len(latest_list),
        "count_tests": len(tests),
    })


@visualizations_bp.route("/fpga-temp/api/test/<int:entry_id>")
def fpga_temp_api_test(entry_id: int):
    if "user_id" not in session:
        abort(401)

    e = TestEntry.query.get(entry_id)
    if not e:
        abort(404)

    serial = _entry_serial(e)
    fpga1, fpga2 = _entry_fpga_temps(e)

    return jsonify({
        "entry_id": e.id,
        "serial": serial,
        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        "fpga1": fpga1,
        "fpga2": fpga2,
        "fpga1_summary": _summarize(fpga1),
        "fpga2_summary": _summarize(fpga2),
    })

@visualizations_bp.route("/fpga-temp/serial/<serial>")
def fpga_temp_serial(serial: str):
    if "user_id" not in session:
        return redirect(url_for("login"))

    # serial stored as digits in DB (based on your _entry_serial)
    serial = str(serial).strip()
    if not serial.isdigit():
        abort(400)

    return render_template("vis/fpga_temp_serial.html", serial=serial)


@visualizations_bp.route("/fpga-temp/api/serial/<serial>")
def fpga_temp_api_serial(serial: str):
    if "user_id" not in session:
        abort(401)

    serial = str(serial).strip()
    if not serial.isdigit():
        abort(400)

    # Pull a bunch of entries; filter in python because CM_serial is inside JSON
    entries = (
        TestEntry.query
        .order_by(desc(TestEntry.timestamp))
        .limit(10000)
        .all()
    )

    tests = []
    for e in entries:
        s = _entry_serial(e)
        if s != serial:
            continue

        fpga1, fpga2 = _entry_fpga_temps(e)
        if not fpga1 and not fpga2:
            continue

        s1 = _summarize(fpga1)
        s2 = _summarize(fpga2)

        tests.append({
            "entry_id": e.id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "fpga1_max": s1["max"],
            "fpga1_avg": s1["avg"],
            "fpga1_n": s1["n"],
            "fpga2_max": s2["max"],
            "fpga2_avg": s2["avg"],
            "fpga2_n": s2["n"],
            "detail_url": url_for("visualizations.fpga_temp_test", entry_id=e.id),
        })

    # reverse to chronological (nice for time series)
    tests.sort(key=lambda r: r["timestamp"] or "")

    return jsonify({
        "serial": serial,
        "tests": tests,
        "count_tests": len(tests),
    })
