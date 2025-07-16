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

import os
import io
import csv
from datetime import datetime, timedelta
from random import randint, uniform, choice #for random
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask import send_from_directory
from werkzeug.utils import secure_filename
from sqlalchemy.orm.attributes import flag_modified #TODO include in the .yml and enviroment if needed later
from models import db, User, TestEntry, EntrySlot, DeletedEntry
from form_config import FORMS, FORMS_NON_DICT

app = Flask(__name__)
app.config['SECRET_KEY'] = 'testsecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

db.init_app(app)

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

def validate_field(field, value, data=None):
    """Validate a single field value based on its type and requirements."""
    if field.validate:
        valid, msg = field.validate(value)
        if not valid:
            print(f"Validation failed for {field.name}: {msg} (value={value})")
            return False, msg

    if field.type_field == "integer":
        if value is None or value == "":
            return False, "This field is required."
        try:
            int(value)
        except ValueError:
            return False, "Must be an integer."
    elif field.type_field == "float":
        if value is None or value == "":
            return False, "This field is required."
        try:
            float(value)
        except ValueError:
            return False, "Must be a number."
    elif field.type_field == "boolean":
        if value not in ("yes", "no"):
            return False, "Please select yes or no."
    elif field.type_field == "file":
        existing = data.get(field.name) if data else None
        if not value and not existing:
            return False, "File is required."
    return True, ""

def validate_form(fields, req, data=None):
    """Validate all fields in the form. Returns (is_valid, errors_dict)."""
    errors = {}
    for field in fields:
        if field.type_field == "file":
            file = req.files.get(field.name)
            value = file.filename if file and file.filename else None
        else:
            value = req.form.get(field.name)
        valid, msg = validate_field(field, value, data)
        if not valid:
            errors[field.name] = msg
    return (len(errors) == 0), errors

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

def determine_step_from_data(data):
    """Return the index of the first incomplete page.
       If everything is filled, return len(FORMS_NON_DICT)."""
    data = data or {}
    for i, page in enumerate(FORMS_NON_DICT):
        for field in page["fields"]:
            fname = getattr(field, "name", None)   # FormField, not dict
            if fname and fname not in data:
                return i
    return len(FORMS_NON_DICT)

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


LOCK_TIMEOUT = timedelta(minutes=20)   # how long before a stale lock is considered free

# fix if user broken and get rid of other one
# def current_user():
#     uid = session.get("user_id")
#     return db.session.get(User, uid) if uid else None


def acquire_lock(entry_id, username):
    """Try to claim the lock; returns (success_flag, entry)."""
    now = datetime.utcnow()

    # ---- new WHERE clause (no imports needed) -----------------
    q = (
        TestEntry.query
        .filter(
            TestEntry.id == entry_id,                     # implicit AND
            (                                             # explicit OR via |
                TestEntry.lock_owner.is_(None) |          #   • lock is free
                (TestEntry.lock_acquired_at + LOCK_TIMEOUT == now)  # • or expired turned off rn TODO fix this or implement it
            )
        )
    )
    # -----------------------------------------------------------

    updated = q.update(
        {"lock_owner": username, "lock_acquired_at": now},
        synchronize_session=False,
    )
    db.session.commit()
    return updated == 1, db.session.get(TestEntry, entry_id)

#TODO put in all submission places
def release_lock(entry):
    """Free the lock on a TestEntry row that you already own."""
    entry.lock_owner = None
    entry.lock_acquired_at = None
    db.session.commit()

def process_file_fields(fields, rq, upload_folder, data):
    """Save uploaded files and update the current data dict with filenames.
    appends uuid to each filename to prevent file overwrites"""
    updated_data = data.copy()
    for field in fields:
        if field.type_field == "file":
            file = rq.files.get(field.name)
            if file and file.filename:
                #save and update
                timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S-%f')
                filename = f"{timestamp}_{secure_filename(file.filename)}"
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                updated_data[field.name] = filename
            else:
                # keep old filename
                if field.name in data:
                    updated_data[field.name] = data[field.name]

    return updated_data

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


## Admin commands for debugging

fishy_users = {}

@app.route('/list_fishy_users')
def list_fishy_users():
    """lists current list of "fishy users" for the current session user becomes fishy by
    attempting to pass a authenticate_admin() check"""

    if not authenticate_admin():
        return "Permission Denied"

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not fishy_users:
        return "No such users"

    return fishy_users

@app.route('/add_dummy_entry')
def add_dummy_entry():
    """Adds dummy entries with randomized values for all non-file fields in FORMS.
        activate with:
        http://localhost:5001/add_dummy_entry → adds 1 entry
        http://localhost:5001/add_dummy_entry?count=10 → adds 10 entries"""

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    try:
        count = int(request.args.get('count', 1))
    except ValueError:
        count = 1

    for _ in range(count):
        test_data = {}

        for form_iter in FORMS:
            for field in form_iter["fields"]:
                name = field.get("name")
                ftype = field.get("type_field")

                if not name or ftype is None:
                    continue

                if ftype == "boolean":
                    test_data[name] = choice(["yes", "no"])
                elif ftype == "integer":
                    test_data[name] = str(randint(3000, 3050)) if name == "CM_serial" else str(randint(0, 9999))
                elif ftype == "float":
                    test_data[name] = f"{uniform(0.0, 10.0):.2f}"
                elif ftype == "text":
                    test_data[name] = "Auto-generated entry"
                elif ftype == "file":
                    test_data[name] = ""  # Leave blank for file fields

        entry = TestEntry(
            user_id=session['user_id'],
            data=test_data,
            timestamp=datetime.utcnow(),
            test=True
        )
        db.session.add(entry)

    db.session.commit()
    return redirect(url_for('history'))

@app.route('/add_dummy_saves')
def add_dummy_saves():
    # activate with http://localhost:5001/add_dummy_saves?entries=N for N entries
    # http://localhost:5001/add_dummy_saves?entries adds one entry

    SERIAL_OFFSET = 3000

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    try:
        num_entries = int(request.args.get('entries', 1))
    except ValueError:
        num_entries = 5

    if 'forms_per_serial' not in session:
        session['forms_per_serial'] = [None] * 51

    used_serials = {
        SERIAL_OFFSET + i for i, val in enumerate(session['forms_per_serial']) if val is not None
    }

    for _ in range(num_entries):
        cm_serial = randint(3000, 3050)
        attempts = 0
        while cm_serial in used_serials and attempts < 20:
            cm_serial = randint(3000, 3050)
            attempts += 1
        if cm_serial in used_serials:
            continue

        used_serials.add(cm_serial)
        index = cm_serial - SERIAL_OFFSET

        entry_data = {
            "CM_serial": cm_serial,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        for form_iter in FORMS:
            for field in form_iter["fields"]:
                if field["type_field"] == "boolean":
                    entry_data[field["name"]] = choice(["yes", "no"])
                elif field["type_field"] == "integer":
                    entry_data[field["name"]] = str(randint(0, 1000))
                elif field["type_field"] == "float":
                    entry_data[field["name"]] = f"{uniform(0, 10):.2f}"
                elif field["type_field"] == "text":
                    entry_data[field["name"]] = "Lorem ipsum"

        # Determine last step with missing fields3
        for i, form_iter in enumerate(FORMS):
            for field in form_iter["fields"]:
                if field["name"] not in entry_data:
                    form_index = i
                    break
            else:
                continue
            break
        else:
            form_index = len(FORMS) - 1

        entry_data['last_step'] = form_index

        session['forms_per_serial'][index] = EntrySlot(
            closed=False,
            data=entry_data,
            test=True
        ).to_dict()

    session.modified = True
    return redirect(url_for('dashboard'))

@app.route('/clear_history')
def clear_history():
    '''clears all entries from history to be removed later'''
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    with app.app_context():
        db.session.query(TestEntry).delete()
        db.session.commit()

        upload_dir = app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                os.remove(file_path)
            except Exception:
                pass  # Silently ignore errors

    return redirect(request.referrer or url_for('history'))

@app.route('/clear_dummy_history')
def clear_dummy_history():
    """clears only entries with test=True from history"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    with app.app_context():
        db.session.query(TestEntry).filter_by(test=True).delete()
        db.session.commit()


        upload_dir = app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                os.remove(file_path)
            except Exception:
                pass  # Silently ignore errors

    return redirect(request.referrer or url_for('history'))

@app.route('/check_dummy_count')
def check_dummy_count():
    """returns number of dummy entires in history"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    count = db.session.query(TestEntry).filter_by(test=True).count()
    return f"Dummy entries: {count}"

@app.route('/clear_saves')
def clear_saves():
    """clears all of current users saves to be removed later or made user friendly (non-admin)"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    session['forms_per_serial'] = [None] * 51
    session.pop('form_data', None)
    session.modified = True

    return redirect(request.referrer or url_for('dashboard'))

@app.route('/clear_dummy_saves')
def clear_dummy_saves():
    """clears all current users saves with test=True (random generated entries)"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    if 'forms_per_serial' in session:
        for i, save in enumerate(session['forms_per_serial']):
            if save and save.get('test'):
                session['forms_per_serial'][i] = None
            session.modified = True

    return redirect(request.referrer or url_for('dashboard'))

# for admin dashboard:

@app.route('/admin/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    forms = (
        TestEntry.query
        .filter(TestEntry.is_finished.is_(False))
        .order_by(TestEntry.timestamp.desc())
        .all()
    )

    return render_template("admin_dashboard.html", forms=forms)

@app.route('/admin/clear_lock/<int:entry_id>', methods=['POST'])
def clear_lock(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    entry = TestEntry.query.get(entry_id)
    if entry and entry.lock_owner:
        entry.lock_owner = None
        db.session.commit()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_form/<int:entry_id>', methods=['POST'])
def delete_form(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    entry = TestEntry.query.get(entry_id)
    user = current_user()
    if entry:
        # Create a DeletedEntry before deleting
        deleted = DeletedEntry(
            original_entry_id=entry.id,
            deleted_by=user.get_username(),
            deleted_at=datetime.utcnow(),
            data=entry.data,
            contributors=entry.contributors,
            fail_reason=entry.fail_reason,
            failure=entry.failure,
            was_locked=entry.lock_owner,
        )
        db.session.add(deleted)
        db.session.delete(entry)
        db.session.commit()

    return redirect(url_for('admin_dashboard'))

# for admin view of deleted entries:

@app.route('/admin/deleted_entries')
def deleted_entries():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    entries = DeletedEntry.query.order_by(DeletedEntry.deleted_at.desc()).all()
    return render_template('deleted_entries.html', entries=entries)




@app.context_processor
def inject_user():
    return dict(current_user=current_user())



def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    user = User.query.get(uid)
    if user is None:
        # Session is stale – user was deleted or DB reset
        session.pop("user_id", None)
    return user

def authenticate_admin():
    """Returns True if current user is admin, False otherwise.
    Logs non-admin or unauthenticated users to fishy_users."""
    user = current_user()
    if not user.administrator:
        username = user.get_username()
        if username in fishy_users:
            fishy_users[username] += 1
        else:
            fishy_users[username] = 1
        return False
    return True

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    app.run(port=5001, debug=True, host='0.0.0.0')
