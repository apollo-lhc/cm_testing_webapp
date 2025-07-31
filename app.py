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
# TODO make test resume button to avoid constantly needing to unlock lock
# TODO fix formatting of code and make constantly repeated code into helper functions
# TODO block people using back button on forms
#TODO get rid of lock and key system and only check if user holds something
#TODO rewrite form route after one form per user gets done
# TODO have files visible in js for form.html

import os
import io
import csv
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, send_from_directory, abort
from sqlalchemy.orm.attributes import flag_modified #TODO include in the .yml and enviroment if needed later

from models import db, User, TestEntry
from form_config import FORMS_NON_DICT
from admin_routes import admin_bp
from admin_form_editor import form_editor_bp
from utils import (validate_form, determine_step_from_data, release_lock, process_file_fields, current_user, acquire_lock)




app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
data_path = os.path.join(basedir, 'data')

app.config['SECRET_KEY'] = 'testsecret'
app.config['UPLOAD_FOLDER'] = 'uploads'

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(data_path, 'test.db')}"
app.config['SQLALCHEMY_BINDS'] = {
    'main': f"sqlite:///{os.path.join(data_path, 'test.db')}",
    'users': f"sqlite:///{os.path.join(data_path, 'users.db')}"
}

db.init_app(app)

app.register_blueprint(admin_bp)
app.register_blueprint(form_editor_bp)

with app.app_context():
    db.create_all()

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Safely serve uploaded files from nested folders like uploads/cm3021/..."""
    # Block path traversal
    if ".." in filename or filename.startswith("/"):
        return abort(400)

    abs_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.isfile(abs_path):
        directory = os.path.dirname(abs_path)
        basename = os.path.basename(abs_path)
        return send_from_directory(directory, basename)
    return abort(404)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # TODO fix ui for this
    """User registration route"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        if User.query.filter_by(username=username).first():
            return 'Error: User already exists'

        new_user = User(username=username)  # type: ignore
        new_user.set_password(request.form['password'])
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html', is_admin_creation=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    #TODO fix ui for this
    """Login form route"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        user = User.query.filter_by(username=username).first()
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

    user = current_user()
    if user is None:
        return redirect(url_for('login'))

    form_index = request.args.get('step')
    form_index = int(form_index or 0)

    # always current user in progress form on correct step
    if request.method == 'GET' and user.form_id is not None:
        held_entry = db.session.get(TestEntry, user.form_id)
        if held_entry:
            last_step = held_entry.data.get("last_step", -1)
            print(f"last step:{last_step}")
            if form_index != last_step:
                session['form_data'] = held_entry.data.copy()
                return redirect(url_for('form', step=last_step))

    if user.form_id is None:
        print("no user-id")

    form_index = max(0, min(form_index, len(FORMS_NON_DICT) - 1))
    current_form = FORMS_NON_DICT[form_index]

    if 'form_data' not in session:
        session['form_data'] = {}

    if request.method == 'POST':

        #errors = {}
        #if "CM_serial" in session['form_data'] and form_index > 0:
            #form_data = request.form.copy()
            #form_data["CM_serial"] = session["form_data"]["CM_serial"]


        # Step 1: update form_data with current inputs
        for field in current_form.fields:
            value = request.form.get(field.name)
            if value is not None:
                session['form_data'][field.name] = value

        session['form_data'] = process_file_fields(current_form.fields, request, app.config['UPLOAD_FOLDER'], session['form_data'])

        # Step 2: mark current step
        session['form_data']['last_step'] = form_index

        # Step 2.5: determine CM_serial and index
        cm_serial = session['form_data'].get("CM_serial")
        serial_error = None

        # check to see if existing entry (saved or failed or in progress) exists
        if form_index == 0:
            posted_serial = request.form.get("CM_serial")

            if posted_serial and posted_serial.isdigit():

                existing_entry = TestEntry.query.filter(
                        TestEntry.data["CM_serial"].as_string() == str(cm_serial),
                        db.or_(
                            TestEntry.is_saved.is_(True),
                            db.and_(
                                TestEntry.failure.is_(True),
                                TestEntry.fail_stored.is_(True),
                                TestEntry.is_finished.is_(False)
                            )
                        )
                    ).first()

                if existing_entry:
                    session.pop('form_data', None)
                    return render_template(
                        "form.html",
                        fields=current_form.fields,
                        prefill_values=session.get('form_data', {}),
                        errors={"CM_serial": f"A form for CM{posted_serial} is already in progress or failed and pending retest."},
                        form_label=current_form.label,
                        name="Form"
                    )

        # Save & Exit
        if request.form.get("save_exit") == "true":
            if serial_error or form_index == 0:
                return render_template(
                    "form.html",
                    fields=current_form.fields,
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error or "Submit Serial Number Before Saving"},
                    form_label=current_form.get("label"),
                    name="Form"
                )

            # Look for an existing in‑progress TestEntry for this serial
            # entry = TestEntry.query.filter(
            #     TestEntry.data["CM_serial"].as_string() == str(cm_serial), TestEntry.is_finished is False
            #     ).first()

            entry = TestEntry.query.filter(TestEntry.id == user.form_id).first()

            if not entry:
                print(f"DEBUG Save - NEW ENTRY - no entry found for user {user.username} with form_id {user.form_id}")
                entry = TestEntry(data={})

            # Merge new data; do NOT overwrite existing uploaded filenames if none chosen
            entry.data.update(session['form_data'])
            flag_modified(entry, "data")
            entry.timestamp = datetime.utcnow()
            entry.failure = False
            entry.fail_reason = None
            entry.fail_stored = False
            entry.is_saved = True

            if user.username not in (entry.contributors or []):
                entry.contributors = (entry.contributors or []) + [user.username]

            user.form_id = None

            db.session.add(entry)
            db.session.commit()
            release_lock(entry)
            session.pop('form_data', None)      # clear browser session copy
            return redirect(url_for('dashboard'))

        # 1st Check for Error Valid Serial Number
        if request.form.get("fail_test_start") == "true":
            if serial_error or form_index == 0:
                return render_template(
                    "form.html",
                    fields=current_form.fields,
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error or "Submit Serial Number Before Submitting Test as Failure"},
                    form_label=current_form.get("label"),
                    name="Form",
                )

            # Renders Form Failure Text Box
            return render_template(
                "form.html",
                fields=current_form.fields,
                prefill_values=session['form_data'],
                errors={},
                form_label=current_form.label,
                name="Form",
                trigger_fail_prompt=True  # passed to js to call text box appear
            )

        # Handle Fail Test Final
        if request.form.get("fail_test") == "true":
            if serial_error:
                return render_template(
                    "form.html",
                    fields=current_form.fields,
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error},
                    form_label=current_form.label,
                    name="Form",
                    trigger_fail_prompt=True
                )

            reason = request.form.get("fail_reason", "").strip()
            user = current_user()

            # Update session data with latest input
            for field in current_form.fields:
                value = request.form.get(field.name)
                if value is not None:
                    session['form_data'][field.name] = value

            session['form_data'] = process_file_fields(
                current_form.fields,
                request,
                app.config['UPLOAD_FOLDER'],
                session['form_data']
            )

            # Update session data with latest input
            for field in current_form.fields:
                value = request.form.get(field.name)
                if value is not None:
                    session['form_data'][field.name] = value

            session['form_data'] = process_file_fields(
                current_form.fields,
                request,
                app.config['UPLOAD_FOLDER'],
                session['form_data']
            )

            # # Find existing in-progress entry to mark as failed
            # entry = TestEntry.query.filter(
            #     TestEntry.data["CM_serial"].as_string() == str(cm_serial), TestEntry.is_finished is False
            # ).first()

            entry = TestEntry.query.filter(TestEntry.id == user.form_id).first()

            if entry:
                entry.data = session['form_data']
                flag_modified(entry, "data")
                entry.is_saved = False  # not in progress anymore

            else:
                print(f"DEBUG - Fail NEW ENTRY - no entry found for user {user.username} with form_id {user.form_id}")
                entry = TestEntry(data=session['form_data'])


            entry.failure = True
            entry.fail_reason = reason
            entry.fail_stored = True
            entry.is_finished = False
            entry.timestamp = datetime.utcnow()

            if user.username not in (entry.contributors or []):
                entry.contributors = (entry.contributors or []) + [user.username]

            user.form_id = None
            db.session.add(entry)
            db.session.commit()
            release_lock(entry)
            entry.is_saved = False

            session.pop('form_data', None)

            return render_template('form_complete.html')

        # Final Submission & Next

        is_valid, errors = validate_form(current_form.fields, request, session.get('form_data'))

        if is_valid:

            entry = TestEntry.query.filter(TestEntry.id == user.form_id).first()

            if not entry:
                entry = TestEntry(data=session['form_data'], is_saved=False)
                db.session.add(entry)
                db.session.flush()
            else:
                if entry.lock_owner and entry.lock_owner != user.username:
                    return "This form is currently being edited by another user."
                entry.data = session['form_data']
                flag_modified(entry, "data")

            entry.timestamp = datetime.utcnow()

            if user.username not in (entry.contributors or []):
                entry.contributors = (entry.contributors or []) + [user.username]

            entry.data['last_step'] = form_index + 1
            flag_modified(entry, "data")
            user.form_id = entry.id
            print(f"assigned {user.username} id: {user.form_id}")

            db.session.commit()

            if form_index + 1 < len(FORMS_NON_DICT):
                return redirect(url_for('form', step=form_index + 1))

            # Final submission - mark complete and final
            entry.is_saved = False
            entry.is_finished = True
            entry.failure = False
            entry.fail_reason = None
            entry.fail_stored = False
            user.form_id = None

            db.session.commit()
            release_lock(entry)
            session.pop('form_data', None)
            return render_template("form_complete.html")


        # Step 5: re-render form with inline errors
        if serial_error:
            errors["CM_serial"] = serial_error

        return render_template(
            "form.html",
            fields=current_form.fields,
            prefill_values=session['form_data'],
            errors=errors,
            form_label=current_form.label,
            name="Form"
        )

    # GET request: load saved state if exists

    #cm_serial = session.get('form_data', {}).get("CM_serial")
    #if cm_serial and cm_serial.isdigit():
        #cm_serial = int(cm_serial)
        #if SERIAL_MIN <= cm_serial <= SERIAL_MAX:
            #index = cm_serial - SERIAL_OFFSET
            #saved = session['forms_per_serial'][index]

            #if saved and not session['form_data']:
                #entry = EntrySlot.from_dict(saved)
                #session['form_data'] = entry.data.copy()


    return render_template(
        "form.html",
        fields=current_form.fields,
        prefill_values=session['form_data'],
        errors={},
        form_label=current_form.label,
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
    for single_form in FORMS_NON_DICT:
        all_fields.extend([f for f in single_form.fields if getattr(f, "display_history", True)])

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

    return render_template('history.html', entries=entries, fields=all_fields, show_unique=unique_toggle, now=datetime.utcnow())

@app.route('/export_csv')
def export_csv():
    """Export all test entries to CSV."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    unique_toggle = request.args.get('unique') == "true"

    # Combine all fields from all forms for CSV export
    all_fields = []
    for single_form in FORMS_NON_DICT:
        all_fields.extend(single_form.fields)


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
    writer.writerow(['Time', 'User'] + [f.label for f in all_fields] + ['File', "Test Aborted", "Reason Aborted"])

    for e in entries:
        row = [e.timestamp, e.user.username]
        row += [e.data.get(f.name) for f in all_fields]
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
        section = getattr(form_iter, "label", "Unnamed Section")
        for field in getattr(form_iter, "fields", []):
            if any([
                getattr(field, "help_text", None),
                getattr(field, "help_link", None),
                getattr(field, "help_label", None)
            ]):
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
            if step_idx >= len(FORMS_NON_DICT)
            else FORMS_NON_DICT[step_idx].label
        )
        e.is_locked = bool(e.lock_owner)

    return render_template("dashboard.html", entries=entries, now=datetime.utcnow())

@app.route('/resume/<int:entry_id>', methods=['POST'])
def resume_entry(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = current_user()

    if user.form_id is not None:
        flash(f"{user.username} already has an inprogress form. Fail or save current test before accessing saved forms", "warning")
        return redirect(url_for('dashboard'))

    success, entry = acquire_lock(entry_id, user.username)
    if not success:
        return "Entry is being edited by someone else. Try again later."

    entry.is_saved = False

    user.form_id = entry.id
    db.session.commit()

    # prime session data and redirect into the normal /form workflow
    session['form_data'] = entry.data.copy()
    step = entry.data.get("last_step", 0)
    return redirect(url_for('form', step=step))

@app.route('/failed_tests')
def failed_tests():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Subquery: get latest timestamp per failed CM_serial
    subquery = (
        db.session.query(
            TestEntry.data["CM_serial"].as_integer().label("cm_serial"),
            db.func.max(TestEntry.timestamp).label("latest")
        )
        .filter(TestEntry.failure.is_(True), TestEntry.fail_stored.is_(True))
        .group_by(TestEntry.data["CM_serial"].as_integer())
        .subquery()
    )

    # Main query: get full entries that match the latest timestamp per serial
    entries = (
        db.session.query(TestEntry)
        .join(subquery, db.and_(
            TestEntry.data["CM_serial"].as_integer() == subquery.c.cm_serial,
            TestEntry.timestamp == subquery.c.latest
        ))
        .order_by(TestEntry.timestamp.desc())
        .all()
    )

    return render_template('failed_tests.html', entries=entries, now=datetime.utcnow())

@app.route('/retest_failed/<int:entry_id>', methods=['POST'])
def retest_failed(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = current_user()

    if user.form_id is not None:
        flash(f"{user.username} already has an inprogress form. Fail or save current test before restarting forms", "warning")
        return redirect(url_for('failed_tests'))


    old_entry = TestEntry.query.get(entry_id)

    if not old_entry or not old_entry.fail_stored:
        flash("This failed test has already been resumed or cleared.", "warning")
        return redirect(url_for('failed_tests'))

    # Mark the old entry as no longer available for retest
    old_entry.fail_stored = False
    db.session.commit()

    retest_data = old_entry.data.copy()
    retest_data["last_step"] = old_entry.data.get("last_step", 0)

    new_entry = TestEntry(
        data=retest_data,
        timestamp=datetime.utcnow(),
        is_finished=False,
        failure=False,
        is_saved=True,
        parent_id=old_entry.id
    )
    if user.username not in (new_entry.contributors or []):
        new_entry.contributors = (new_entry.contributors or []) + [user.username]
    db.session.add(new_entry)
    db.session.commit()

    user.form_id = new_entry.id
    print(f"new user you form_id: {user.form_id}")
    db.session.commit()

    session['form_data'] = retest_data.copy()
    return redirect(url_for('form', step=retest_data["last_step"]))

@app.route('/clear_failed/<int:entry_id>', methods=['POST'])
def clear_failed(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    entry = TestEntry.query.get(entry_id)
    if entry and entry.failure and entry.fail_stored:
        entry.fail_stored = False
        entry.is_finished = True
        db.session.commit()

    return redirect(url_for('failed_tests'))

@app.context_processor
def inject_user():
    return {"current_user": current_user}

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    app.run(port=5001, debug=True, host='0.0.0.0')
