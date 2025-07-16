"""
Flask web application for managing test entries with user authentication.

Features:
- User registration and login
- Form submission for test data with file upload
- History view of all test entries
- CSV export of test results
- File download for uploaded reports
"""

#TODO fix prompt for login on trying to recieve lock after not being logged in in same session
# TODO fix datetimes to all match cornell's timezone
# TODO remove entryslot entirely (entryslot -> testentries)
# TODO move resume entry and lock and other routes out of admin routes

import os
import io
import csv
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask import send_from_directory
from sqlalchemy.orm.attributes import flag_modified #TODO include in the .yml and enviroment if needed later
from models import db, User, TestEntry, EntrySlot
from form_config import FORMS, FORMS_NON_DICT
from admin_routes import admin_bp
from utils import (validate_form, determine_step_from_data, release_lock, process_file_fields, current_user, acquire_lock)


app = Flask(__name__)

app.config['SECRET_KEY'] = 'testsecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

db.init_app(app)

app.register_blueprint(admin_bp)


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin')  # type: ignore
        admin.set_password('password')
        admin.administrator = True
        db.session.add(admin)
        logan = User(username='logan')  # type: ignore
        logan.set_password('prosser')
        logan.administrator = True
        db.session.add(logan)
        db.session.commit()

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """route to serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route"""
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            return 'Error: User already exists'
        new_user = User(username=request.form['username'])  # type: ignore
        new_user.set_password(request.form['password'])
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """login form route"""
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            session['user_id'] = user.id
            return redirect(url_for('home'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    """logout route"""
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/')
def home():
    """home page route"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/form', methods=['GET', 'POST'])
def form():
    """form submission save and failure function"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    SERIAL_OFFSET = 3000 # to prevent wasting memory make this the first serial number so 'forms_per_serial'[0] maps to CM3000

    form_index = request.args.get('step')
    if form_index is None:
        cm_serial = session.get('form_data', {}).get("CM_serial")
        if cm_serial and cm_serial.isdigit():
            index = int(cm_serial) - SERIAL_OFFSET
            if 0 <= index < len(session['forms_per_serial']):
                saved = session['forms_per_serial'][index]
                if saved:
                    entry = EntrySlot.from_dict(saved)
                    form_index = entry.data.get('last_step', 0)


    form_index = int(form_index or 0)
    form_index = max(0, min(form_index, len(FORMS_NON_DICT) - 1))
    current_form = FORMS_NON_DICT[form_index]

    if 'form_data' not in session:
        session['form_data'] = {}

    if 'forms_per_serial' not in session:
        session['forms_per_serial'] = [None] * 51

    if request.method == 'POST':
        errors = {}
        if "CM_serial" in session['form_data'] and form_index > 0:
            request.form = request.form.copy()
            request.form["CM_serial"] = session["form_data"]["CM_serial"]

        # Step 1: update form_data with current inputs
        for field in current_form["fields"]:
            value = request.form.get(field.name)
            if value is not None:
                session['form_data'][field.name] = value

        session['form_data'] = process_file_fields(current_form["fields"], request, app.config['UPLOAD_FOLDER'], session['form_data'])

        # Step 2: mark current step
        session['form_data']['last_step'] = form_index

        # Step 2.5: determine CM_serial and index
        cm_serial = session['form_data'].get("CM_serial")
        index = None
        serial_error = None

        if cm_serial and cm_serial.isdigit():
            cm_serial = int(cm_serial)
            if 3000 <= cm_serial <= 3050:
                index = cm_serial - SERIAL_OFFSET
            else:
                serial_error = "Must be between 3000 and 3050"
        else:
            serial_error = "Must be an integer between 3000 and 3050"

        if form_index == 0:
            posted_serial = request.form.get("CM_serial")

            if posted_serial and posted_serial.isdigit():
                existing_entry = (
                    TestEntry.query
                    .filter(TestEntry.data["CM_serial"].as_string() == str(posted_serial),
                            TestEntry.is_saved.is_(True))
                    .first()
                )

                if existing_entry:
                    session.pop('form_data', None)
                    return render_template(
                        "form.html",
                        fields=current_form["fields"],
                        prefill_values=session.get('form_data', {}),
                        errors={"CM_serial": f"A form for CM{posted_serial} is already in progress. You must complete or close it before starting a new one."},
                        form_label=current_form.get("label"),
                        name="Form"
                    )



        # Step 3: handle Save & Exit
        if request.form.get("save_exit") == "true":
            if serial_error:
                return render_template(
                    "form.html",
                    fields=current_form["fields"],
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error},
                    form_label=current_form.get("label"),
                    name="Form"
                )

            # ---------- GLOBAL SAVE ----------
            user = current_user()
            cm_serial = session['form_data'].get("CM_serial")
            # form index = 0 required to be serial number only see asserts in form_config
            if form_index == 0:
                return render_template(
                    "form.html",
                    fields=current_form["fields"],
                    prefill_values=session['form_data'],
                    errors={"CM_serial": "Submit Serial Number Before Saving"},
                    form_label=current_form.get("label"),
                    name="Form"
                )


            # Look for an existing in‑progress TestEntry for this serial
            entry = (TestEntry.query
                    .filter(TestEntry.data["CM_serial"].as_string() == str(cm_serial),
                            TestEntry.is_saved.is_(True))
                    .first())

            # confirm_overwrite = request.form.get("confirm_overwrite") == "true"

            # if entry and not confirm_overwrite:
            #     return render_template(
            #         "form.html",
            #         fields=current_form["fields"],
            #         prefill_values=session['form_data'],
            #         errors={"CM_serial": "This serial number already has a saved form."},
            #         form_label=current_form.get("label"),
            #         name="Form",
            #         show_overwrite_prompt=True,
            #         existing_timestamp=entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            #     )

            if not entry:
                entry = TestEntry(data={}, is_saved=True)

            # Merge new data; do NOT overwrite existing uploaded filenames if none chosen
            entry.data.update(session['form_data'])
            flag_modified(entry, "data")
            if user.username not in (entry.contributors or []):
                entry.contributors = (entry.contributors or []) + [user.username]
            entry.timestamp = datetime.utcnow()
            db.session.add(entry)
            db.session.commit()
            release_lock(entry)
            session.pop('form_data', None)      # clear browser session copy
            return redirect(url_for('dashboard'))

            # if index is not None: # number assigned to store in users saved tests

            #     if 'timestamp' not in session['form_data']:
            #         session['form_data']['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            #     session['forms_per_serial'][index] = EntrySlot(
            #         closed=False,
            #         data=session['form_data'].copy()
            #     ).to_dict()
            #     session.modified = True

            # return redirect(url_for('dashboard'))

        # 1st Check for Error Valid Serial Number
        if request.form.get("fail_test_start") == "true":
            if serial_error:
                return render_template(
                    "form.html",
                    fields=current_form["fields"],
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error},
                    form_label=current_form.get("label"),
                    name="Form",
                )

            if form_index == 0:
                return render_template(
                    "form.html",
                    fields=current_form["fields"],
                    prefill_values=session['form_data'],
                    errors={"CM_serial": "Submit Serial Number Before Submitting Test as Failure"},
                    form_label=current_form.get("label"),
                    name="Form"
                )

            return render_template(
                "form.html",
                fields=current_form["fields"],
                prefill_values=session['form_data'],
                errors={},
                form_label=current_form.get("label"),
                name="Form",
                trigger_fail_prompt=True  # passed to js to call text box appear
            )

        # Handle Fail Test Final
        if request.form.get("fail_test") == "true":
            if serial_error:
                return render_template(
                    "form.html",
                    fields=current_form["fields"],
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error},
                    form_label=current_form.get("label"),
                    name="Form",
                    trigger_fail_prompt=True
                )

            reason = request.form.get("fail_reason", "").strip()
            user = current_user()

            # Update session data with latest input
            for field in current_form["fields"]:
                value = request.form.get(field.name)
                if value is not None:
                    session['form_data'][field.name] = value

            session['form_data'] = process_file_fields(
                current_form["fields"],
                request,
                app.config['UPLOAD_FOLDER'],
                session['form_data']
            )

            # Find existing in-progress entry to mark as failed
            entry = (
                TestEntry.query
                .filter(TestEntry.data["CM_serial"].as_string() == str(cm_serial),
                        TestEntry.is_saved.is_(True))
                .first()
            )
            if entry:
                entry.data = session['form_data']
                flag_modified(entry, "data")
                entry.failure = True
                entry.fail_reason = reason
                entry.is_saved = False  # not in progress anymore
                entry.timestamp = datetime.utcnow()

                if entry.lock_owner:
                    release_lock(entry)
            else:
                # fallback if no saved form found
                entry = TestEntry(
                    data=session['form_data'],
                    timestamp=datetime.utcnow(),
                    failure=True,
                    fail_reason=reason)

                db.session.add(entry)

            if user.username not in (entry.contributors or []):
                entry.contributors = (entry.contributors or []) + [user.username]

            entry.is_finished = True
            db.session.commit()

            if index is not None:
                session['forms_per_serial'][index] = None
                session.modified = True

            session.pop('form_data', None)

            return render_template('form_complete.html')

        # Step 4: full validation for Next
        if request.form.get("fail_test_start") != "true": #unnecessary if fix it
            is_valid, errors = validate_form(current_form["fields"], request, session.get('form_data'))

            if is_valid:
                if index is not None:
                    if 'timestamp' not in session['form_data']:
                        session['form_data']['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    session['forms_per_serial'][index] = EntrySlot(
                        closed=False,
                        data=session['form_data'].copy()
                    ).to_dict()
                    session.modified = True

                # To submit or create test entry each time user hits next on a form page to show in progress forms and for serial lock full funcitonality
                user = current_user()

                entry = (TestEntry.query
                         .filter(TestEntry.data["CM_serial"].as_string() == str(cm_serial),
                                 TestEntry.is_saved.is_(True))
                         .first()
                )

                if not entry:
                    entry = TestEntry(data=session['form_data'], is_saved=True)
                    db.session.add(entry)
                else:
                    if entry.lock_owner and entry.lock_owner != user.username:
                        return "This form is currently being edited by another user."
                    entry.data = session['form_data']
                    flag_modified(entry, "data")

                if user.username not in (entry.contributors or []):
                    entry.contributors = (entry.contributors or []) + [user.username]

                entry.timestamp = datetime.utcnow()
                entry.is_saved = True
                db.session.commit()

                if form_index + 1 < len(FORMS):
                    return redirect(url_for('form', step=form_index + 1))

                # Final submission
                user = db.session.get(User, session['user_id'])
                entry = TestEntry(data=session['form_data'], timestamp=datetime.now())
                if user.username not in (entry.contributors or []):
                    entry.contributors = (entry.contributors or []) + [user.username]
                release_lock(entry)
                entry.is_finished = True
                db.session.add(entry)
                db.session.commit()

                if index is not None:
                    session['forms_per_serial'][index] = None
                    session.modified = True
                session.pop('form_data', None)

                return render_template('form_complete.html')

        # Step 5: re-render form with inline errors
        if serial_error:
            errors["CM_serial"] = serial_error

        return render_template(
            "form.html",
            fields=current_form["fields"],
            prefill_values=session['form_data'],
            errors=errors,
            form_label=current_form.get("label"),
            name="Form"
        )

    # GET request: load saved state if exists
    cm_serial = session.get('form_data', {}).get("CM_serial")
    if cm_serial and cm_serial.isdigit():
        cm_serial = int(cm_serial)
        if 3000 <= cm_serial <= 3050:
            index = cm_serial - SERIAL_OFFSET
            saved = session['forms_per_serial'][index]

            if saved and not session['form_data']:
                entry = EntrySlot.from_dict(saved)
                session['form_data'] = entry.data.copy()

    return render_template(
        "form.html",
        fields=current_form["fields"],
        prefill_values=session['form_data'],
        errors={},
        form_label=current_form.get("label"),
        name="Form"
    )

@app.route('/restart_forms')
def restart_forms():
    """Restart the multi-form entry process."""
    session.pop('form_index', None)
    session.pop('form_data', None)
    session.pop('file_name', None)
    return redirect(url_for('form'))

@app.route('/history')
def history():
    """Show history of all test entries."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    unique_toggle = request.args.get('unique') == "true"

    all_fields = []
    for single_form in FORMS:
        all_fields.extend([f for f in single_form["fields"] if f.get("display_history", True)])

    if unique_toggle:
        subquery = (
            db.session.query(
                TestEntry.data["CM_serial"].as_integer().label("cm_serial"),
                db.func.max(TestEntry.timestamp).label("latest")
            )
            .group_by(TestEntry.data["CM_serial"].as_integer())
            .subquery()
        )

        entries = (
            db.session.query(TestEntry)
            .join(subquery, db.and_(
                TestEntry.data["CM_serial"].as_integer() == subquery.c.cm_serial,
                TestEntry.timestamp == subquery.c.latest
            ))
            .order_by(TestEntry.timestamp.desc())
            .all()
        )

    else:
        entries = TestEntry.query.order_by(TestEntry.timestamp.desc()).all()

    return render_template('history.html', entries=entries, fields=all_fields, show_unique=unique_toggle)

@app.route('/export_csv')
def export_csv():
    """Export all test entries to CSV."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    unique_toggle = request.args.get('unique') == "true"

    # Combine all fields from all forms for CSV export
    all_fields = []
    for single_form in FORMS:
        all_fields.extend(single_form["fields"])

    if unique_toggle:
        subquery = (
            db.session.query(
                TestEntry.data["CM_serial"].as_integer().label("cm_serial"),
                db.func.max(TestEntry.timestamp).label("latest")
            )
            .group_by(TestEntry.data["CM_serial"].as_integer())
            .subquery()
        )

        entries = (
            db.session.query(TestEntry)
            .join(subquery, db.and_(
                TestEntry.data["CM_serial"].as_integer() == subquery.c.cm_serial,
                TestEntry.timestamp == subquery.c.latest
            ))
            .order_by(TestEntry.timestamp.desc())
            .all()
        )
    else:
        entries = TestEntry.query.order_by(TestEntry.timestamp.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Time', 'User'] + [f["label"] for f in all_fields] + ['File', "Test Aborted", "Reason Aborted"])

    for e in entries:
        row = [e.timestamp, e.user.username]
        row += [e.data.get(f["name"]) for f in all_fields]
        row += [e.file_name, "yes" if e.failure else "no", e.fail_reason or ""]
        writer.writerow(row)

    output.seek(0)
    return send_file(io.BytesIO(output.read().encode()), mimetype='text/csv',
                     as_attachment=True, download_name='test_results.csv')

@app.route('/help')
def help_button():
    """Render help page grouped by form section, showing only fields with help_text, help_link, or help_label."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    grouped_help_fields = {}

    for form_iter in FORMS_NON_DICT:
        section = form_iter.get("label", "Unnamed Section")
        for field in form_iter.get("fields", []):
            if any([
                getattr(field, "help_text", None),
                getattr(field, "help_link", None),
                getattr(field, "help_label", None)
            ]):
                getattr(field, "label", None)
                if section not in grouped_help_fields:
                    grouped_help_fields[section] = []
                grouped_help_fields[section].append(field)

    return render_template("help.html", grouped_help_fields=grouped_help_fields)

@app.route('/prod_test_doc')
def prod_test_doc():
    """Bring up Apollo Production Testing Document."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return send_from_directory("static", "Apollo_CMv3_Production_Testing_04Nov2024.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    entries = (
        TestEntry.query
        .filter_by(is_saved=True)
        .order_by(TestEntry.timestamp.desc())
        .all()
    )

    for e in entries:
        step_idx = e.data.get("last_step")
        if step_idx is None:
            step_idx = determine_step_from_data(e.data)

        try:
            step_idx = int(step_idx)
        except (ValueError, TypeError):
            step_idx = 0

        e.step_label = (
            "Finished"
            if step_idx >= len(FORMS)
            else FORMS[step_idx]["label"]
        )
        e.is_locked = bool(e.lock_owner)

    return render_template("dashboard.html", entries=entries, now=datetime.utcnow())

@app.route('/resume/<int:entry_id>', methods=['POST'])
def resume_entry(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = current_user()
    success, entry = acquire_lock(entry_id, user.username)
    if not success:
        return "Entry is being edited by someone else. Try again later."

    # prime session data and redirect into the normal /form workflow
    session['form_data'] = entry.data.copy()
    step = entry.data.get("last_step", 0)
    return redirect(url_for('form', step=step))

@app.context_processor
def inject_user():
    return dict(current_user=current_user())

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    app.run(port=5001, debug=True, host='0.0.0.0')
