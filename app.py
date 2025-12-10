"""
Flask web application for managing test entries with user authentication.

Features:
- User registration and login
- Form submission for test data with file upload
- History view of all test entries
- CSV export of test results
- File download for uploaded reports
"""
# TODO fix formatting of code and make constantly repeated code into helper functions?
# TODO block using back button on forms?
# TODO have files visible in js for form.html
# TODO make a @loginrequired

import os
import io
import csv
import json
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, send_from_directory, abort
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import and_


from models import db, User, TestEntry
from form_config import FORMS_NON_DICT
from admin_routes import admin_bp
from admin_form_editor import form_editor_bp
from utils import validate_form, determine_step_from_data, release_lock, process_file_fields, current_user, acquire_lock, get_page_map
from constants import EASTERN_TZ

app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
data_path = os.path.join(basedir, 'data')

# set secret key from environment variable for session management (inside run.sh or before starting)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is not set")

app.config['UPLOAD_FOLDER'] = 'uploads'

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(data_path, 'test.db')}"
app.config['SQLALCHEMY_BINDS'] = {
    'main': f"sqlite:///{os.path.join(data_path, 'test.db')}",
    'users': f"sqlite:///{os.path.join(data_path, 'users.db')}"
}

app.config['SESSION_COOKIE_SECURE'] = False       # allow HTTP
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'     # 'None' on HTTP will be rejected
app.config['SESSION_COOKIE_HTTPONLY'] = True


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
    """User registration route"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        if User.query.filter_by(username=username).first():
            flash("User already exists.", "error")
            return render_template('register.html')

        new_user = User(username=username)  # type: ignore
        new_user.set_password(request.form['password'])
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html', is_admin_creation=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        print("DEBUG /login payload:",
            "js_ready=", request.form.get('js_ready'),
            "keys=", list(request.form.keys()),
            "password.len=", len(request.form.get('password', "")))
        # continue with your existing logic...
        username = request.form['username'].strip()
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            return redirect(url_for('home'))

        flash("Invalid username or password.", "error")
        return render_template('login.html')

    return render_template('login.html')

@app.route('/form_complete')
def form_complete():
    """Render form completion page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    return render_template('form_complete.html')

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

@app.route("/entry/<int:entry_id>/form_home")
def form_home(entry_id):
    """Hub page showing all sections and their completion status."""
    
    if "user_id" not in session:
        return redirect(url_for("login"))

    entry = TestEntry.query.get_or_404(entry_id)

    data = entry.data or {}

    pages = FORMS_NON_DICT[1:]
    completion = {}

    for i, page in enumerate(pages):
        # the FIRST PAGE (serial page) should never show
        if i == 0:
            continue
        
        done = True
        for field in page.fields:
            if not field.display_form:
                continue

            val = data.get(field.name)

            if val in (None, "", []):
                done = False
                break

        completion[page.name] = done

    return render_template(
        "form_home.html",
        entry=entry,
        pages=pages,
        completion=completion
    )



if 1 == 9:
        
    print("hey")
    # @app.route("/entry/<int:entry_id>/form/<page_name>", methods=["GET", "POST"])
    # def form_page(entry_id, page_name):
    #     if "user_id" not in session:
    #         return redirect(url_for("login"))

    #     user = current_user()
    #     entry = TestEntry.query.get_or_404(entry_id)

    #     # Lock check
    #     if entry.lock_owner and entry.lock_owner != user.username:
    #         return "This form is currently being edited by another user."

    #     page_map = get_page_map()
    #     page = page_map.get(page_name)
    #     if page is None:
    #         abort(404)

    #     data = entry.data or {}

    #     # =================================================================
    #     # POST handling
    #     # =================================================================
    #     if request.method == "POST":

    #         # Update this page’s fields only
    #         for field in page.fields:
    #             if not field.display_form:
    #                 continue
    #             value = field.get_value(request)
    #             if value is not None:
    #                 data[field.name] = value

    #         # File upload processing
    #         data.update(
    #             process_file_fields(
    #                 page.fields, request, app.config["UPLOAD_FOLDER"], data
    #             )
    #         )

    #         entry.data = data
    #         flag_modified(entry, "data")

    #         cm_serial = data.get("CM_serial")

    #         # =====================================================================
    #         # 1) SAVE & RETURN HOME — MUST SHORT-CIRCUIT EARLY AND MUST NOT VALIDATE
    #         # =====================================================================
    #         if request.form.get("save_home") == "true":
    #             print("[DEBUG] Save & Return HOME triggered.")
    #             if not cm_serial:
    #                 return render_template(
    #                     "form.html",
    #                     fields=page.fields,
    #                     prefill_values=data,
    #                     errors={"CM_serial": "Submit Serial Number Before Saving"},
    #                     form_label=page.label,
    #                     entry_id=entry.id
    #                 )

                
                
    #             entry.timestamp = datetime.now(EASTERN_TZ)
    #             entry.is_saved = True  # Partial save

    #             if user.username not in (entry.contributors or []):
    #                 entry.contributors = entry.contributors + [user.username]

    #             db.session.commit()

    #             print("[DEBUG] Save & Return HOME executed. No Next. No validation.")

    #             # CRITICAL: RETURN IMMEDIATELY
    #             return redirect(url_for("form_home", entry_id=entry.id))

    #         # =====================================================================
    #         # 2) SAVE & EXIT (same as old)
    #         # =====================================================================
    #         if request.form.get("save_exit") == "true":
    #             if not cm_serial:
    #                 return render_template(
    #                     "form.html",
    #                     fields=page.fields,
    #                     prefill_values=data,
    #                     errors={"CM_serial": "Submit Serial Number Before Saving"},
    #                     form_label=page.label,
    #                     entry_id=entry.id,
    #                 )

    #             entry.timestamp = datetime.now(EASTERN_TZ)
    #             entry.is_saved = True
    #             entry.failure = False
    #             entry.fail_reason = None
    #             entry.fail_stored = False

    #             if user.username not in entry.contributors:
    #                 entry.contributors.append(user.username)

    #             db.session.commit()
    #             release_lock(entry)
    #             user.form_id = None
    #             db.session.commit()

    #             return redirect(url_for("dashboard"))

    #         # =====================================================================
    #         # 3) FAIL TEST START
    #         # =====================================================================
    #         if request.form.get("fail_test_start") == "true":
    #             print("[DEBUG] Fail Test START triggered.")
    #             if not cm_serial:
    #                 return render_template(
    #                     "form.html",
    #                     fields=page.fields,
    #                     prefill_values=data,
    #                     errors={"CM_serial": "Submit Serial Number Before Submitting Test as Failure"},
    #                     form_label=page.label,
    #                     entry_id=entry.id,
    #                     trigger_fail_prompt=False
    #                 )
    #             return render_template(
    #                 "form.html",
    #                 fields=page.fields,
    #                 prefill_values=data,
    #                 errors={},
    #                 form_label=page.label,
    #                 entry_id=entry.id,
    #                 trigger_fail_prompt=True
    #             )

    #         # =====================================================================
    #         # 4) FAIL TEST FINAL
    #         # =====================================================================
    #         if request.form.get("fail_test") == "true":
    #             print("[DEBUG] Fail Test FINAL triggered.")
    #             if not cm_serial:
    #                 return render_template(
    #                     "form.html",
    #                     fields=page.fields,
    #                     prefill_values=data,
    #                     errors={"CM_serial": "Submit Serial Number Before Failing Test"},
    #                     form_label=page.label,
    #                     entry_id=entry.id,
    #                     trigger_fail_prompt=True
    #                 )

    #             reason = request.form.get("fail_reason", "").strip()

    #             entry.failure = True
    #             entry.fail_reason = reason
    #             entry.fail_stored = True
    #             entry.is_finished = False
    #             entry.is_saved = False
    #             entry.timestamp = datetime.now(EASTERN_TZ)

    #             if user.username not in entry.contributors:
    #                 entry.contributors.append(user.username)

    #             db.session.commit()
    #             release_lock(entry)
    #             user.form_id = None
    #             db.session.commit()

    #             return render_template("form_complete.html")

    #         # =====================================================================
    #         # 5) NEXT — VALIDATE AND MOVE FORWARD
    #         # =====================================================================
    #         if request.form.get("next") == "true":
    #             print("[DEBUG] Next triggered.")
    #             # Full validation
    #             ok, errors = validate_form(page.fields, request, data)
    #             if not ok:
    #                 return render_template(
    #                     "form.html",
    #                     fields=page.fields,
    #                     prefill_values=data,
    #                     errors=errors,
    #                     form_label=page.label,
    #                     entry_id=entry.id
    #                 )

    #             # Go to next page
    #             pages = FORMS_NON_DICT
    #             idx = next((i for i, p in enumerate(pages) if p.name == page.name), None)
    #             if idx is not None and idx + 1 < len(pages):
    #                 next_page = pages[idx + 1].name
    #                 entry.is_saved = True
    #                 db.session.commit()
    #                 return redirect(url_for("form_page", entry_id=entry.id, page_name=next_page))

    #             # End of form → go to review
    #             entry.is_saved = True
    #             db.session.commit()
    #             return redirect(url_for("review_entry", entry_id=entry.id))

    #         # =====================================================================
    #         # DEFAULT fallthrough
    #         # =====================================================================
    #         db.session.commit()
    #         return redirect(url_for("form_page", entry_id=entry.id, page_name=page.name))

    #     # =================================================================
    #     # GET
    #     # =================================================================
    #     return render_template(
    #         "form.html",
    #         fields=page.fields,
    #         prefill_values=data,
    #         errors={},
    #         form_label=page.label,
    #         entry_id=entry.id
    #     )

    # @app.route("/entry/<int:entry_id>/form/<page_name>", methods=["GET", "POST"])
    # def form_page(entry_id, page_name):
    #     """
    #     Minimal clean form page route that supports:
    #       - GET: load page
    #       - POST: partial save
    #       - next, save_home, save_exit buttons
    #     """

    #     if "user_id" not in session:
    #         return redirect(url_for("login"))
        
    #     user = current_user()
    #     entry = TestEntry.query.get_or_404(entry_id)

    #     # Lock check (optional)
    #     if entry.lock_owner and entry.lock_owner != user.username:
    #         return "This form is currently being edited by another user."

    #     # Page object lookup
    #     page_map = {p.name: p for p in FORMS_NON_DICT}
    #     page = page_map.get(page_name)
    #     if page is None:
    #         abort(404)

    #     # Ensure entry.data exists
    #     if entry.data is None:
    #         entry.data = {}

    #     data = entry.data

    #     # =============================
    #     # POST — save partial changes
    #     # =============================
    #     if request.method == "POST":

    #         # Update fields
    #         for field in page.fields:
    #             if not field.display_form:
    #                 continue

    #             val = field.get_value(request)
    #             if val is not None:
    #                 data[field.name] = val

    #         # Save files
    #         data.update(
    #             process_file_fields(page.fields, request, app.config["UPLOAD_FOLDER"], data)
    #         )

    #         entry.data = data
    #         flag_modified(entry, "data")
    #         entry.timestamp = datetime.now(EASTERN_TZ)

    #         # Track contributor
    #         if user.username not in (entry.contributors or []):
    #             entry.contributors = (entry.contributors or []) + [user.username]

    #         # =========================
    #         # BUTTON: Save & Return Home
    #         # =========================
    #         if request.form.get("save_home") == "true":
    #             print("DEBUG: Save & Return Home button clicked FORM PAGE ROUTE")
    #             db.session.commit()
    #             return redirect(url_for("form_home", entry_id=entry.id))

    #         # =========================
    #         # BUTTON: Save & Exit
    #         # =========================
    #         if request.form.get("save_exit") == "true":
    #             print("DEBUG: Save & Exit button clicked FORM PAGE ROUTE")
    #             entry.is_saved = True
    #             db.session.commit()
    #             return redirect(url_for("dashboard"))

    #         # =========================
    #         # BUTTON: Next
    #         # =========================
    #         if request.form.get("next") == "true":
    #             print("DEBUG: Next button clicked FORM PAGE ROUTE")
    #             pages = FORMS_NON_DICT
    #             i = next((idx for idx, p in enumerate(pages) if p.name == page_name), None)

    #             if i is not None and i + 1 < len(pages):
    #                 # go to next page
    #                 db.session.commit()
    #                 return redirect(url_for("form_page",
    #                                         entry_id=entry.id,
    #                                         page_name=pages[i + 1].name))

    #             # last page → go to review or completion page
    #             db.session.commit()
    #             return redirect(url_for("review_entry", entry_id=entry.id))

    #         # Default behavior: save & stay on same page
    #         db.session.commit()
    #         return redirect(url_for("form_page", entry_id=entry.id, page_name=page.name))

    #     # =============================
    #     # GET — show page
    #     # =============================
    #     return render_template(
    #         "form.html",
    #         fields=page.fields,
    #         prefill_values=data,
    #         form_label=page.label,
    #         entry_id=entry.id,
    #         errors={}
    #     )


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
            #DEBUG PRINT
            #print(f"last step:{last_step}")
            if form_index != last_step:
                session['form_data'] = held_entry.data.copy()
                return redirect(url_for('form', step=last_step))

    # #DEBUG PRINT
    # if user.form_id is None:
    #     print("no user-id")

    form_index = max(0, min(form_index, len(FORMS_NON_DICT) - 1))
    current_form = FORMS_NON_DICT[form_index]

    if 'form_data' not in session:
        session['form_data'] = {}

    if request.method == 'POST':

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
                    
        # Save & Exit to Form Home Page
        if request.form.get("save_home") == "true":
            print("[DEBUG] Save & Exit Home Page triggered. OLD FORM")
            if serial_error or form_index == 0:
                return render_template(
                    "form.html",
                    fields=current_form.fields,
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error or "Submit Serial Number Before Saving"},
                    form_label=current_form.label,
                    entry_id=user.form_id,
                    name="Form"
                )

            entry = TestEntry.query.filter(TestEntry.id == user.form_id).first()

            if not entry:
                #DEBUG PRINT
                #print(f"DEBUG Save - NEW ENTRY - no entry found for user {user.username} with form_id {user.form_id}")
                entry = TestEntry(data={})

            # Merge new data; do NOT overwrite existing uploaded filenames if none chosen
            entry.data.update(session['form_data'])
            flag_modified(entry, "data")
            entry.timestamp = datetime.now(EASTERN_TZ)
            entry.failure = False
            entry.fail_reason = None
            entry.fail_stored = False
            # entry.is_saved = True

            if user.username not in (entry.contributors or []):
                entry.contributors = (entry.contributors or []) + [user.username]

            # user.form_id = None

            db.session.add(entry)
            db.session.commit()
            # release_lock(entry)
            # session.pop('form_data', None)      # clear browser session copy
            return redirect(url_for("form_home", entry_id=entry.id))

        # Save & Exit
        if request.form.get("save_exit") == "true":
            print("[DEBUG] Save & Exit triggered. OLD FORM")
            if serial_error or form_index == 0:
                return render_template(
                    "form.html",
                    fields=current_form.fields,
                    prefill_values=session['form_data'],
                    errors={"CM_serial": serial_error or "Submit Serial Number Before Saving"},
                    form_label=current_form.label,
                    name="Form"
                )

            entry = TestEntry.query.filter(TestEntry.id == user.form_id).first()

            if not entry:
                #DEBUG PRINT
                #print(f"DEBUG Save - NEW ENTRY - no entry found for user {user.username} with form_id {user.form_id}")
                entry = TestEntry(data={})

            # Merge new data; do NOT overwrite existing uploaded filenames if none chosen
            entry.data.update(session['form_data'])
            flag_modified(entry, "data")
            entry.timestamp = datetime.now(EASTERN_TZ)
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
                    form_label=current_form.label,
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

            entry = TestEntry.query.filter(TestEntry.id == user.form_id).first()

            if entry:
                entry.data = session['form_data']
                flag_modified(entry, "data")
                entry.is_saved = False  # not in progress anymore

            else:
                #DEBUG PRINT
                #print(f"DEBUG - Fail NEW ENTRY - no entry found for user {user.username} with form_id {user.form_id}")
                entry = TestEntry(data=session['form_data'])


            entry.failure = True
            entry.fail_reason = reason
            entry.fail_stored = True
            entry.is_finished = False
            entry.timestamp = datetime.now(EASTERN_TZ)

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
        print("[DEBUG] Final Submission & Next triggered. OLD FORM")
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

            entry.timestamp = datetime.now(EASTERN_TZ)

            if user.username not in (entry.contributors or []):
                entry.contributors = (entry.contributors or []) + [user.username]

            entry.data['last_step'] = form_index + 1
            flag_modified(entry, "data")
            user.form_id = entry.id

            #DEBUG PRINT
            #print(f"assigned {user.username} id: {user.form_id}")

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

    return render_template('history.html', entries=entries, fields=all_fields, show_unique=unique_toggle, now=datetime.now(EASTERN_TZ))

@app.route('/entry/<int:entry_id>')
def entry_detail(entry_id):
    """Expanded view of entry."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    entry = db.session.get(TestEntry, entry_id)

    if not entry:
        flash(f"No entry found with ID{entry_id}.", "warning")
        return redirect(url_for('history'))

    # collect all visible fields (like in /history)
    all_fields = []
    for form_page in FORMS_NON_DICT:
        all_fields.extend([f for f in form_page.fields if getattr(f, "display_history", True)])

    return render_template(
        "entry_detail.html",
        entry=entry,
        fields=all_fields,
    )

@app.route('/export_csv')
def export_csv():
    """Export only visible (display_history=True) fields to CSV."""
    if 'user_id' not in session:
        return redirect(url_for('login'))



    unique_toggle = request.args.get('unique') == "true"

    # ---------- 1) Only include visible fields ----------
    visible_fields = []
    for page in FORMS_NON_DICT:
        for field in getattr(page, "fields", []) or []:
            if getattr(field, "display_history", False):
                visible_fields.append(field)

    # ---------- 2) Prepare serializer to clean up text ----------
    clean_ws = re.compile(r"[\r\n\t]+")
    def safe(val):
        if val is None:
            return ""
        if isinstance(val, datetime):
            return val.replace(microsecond=0).isoformat(sep=" ")
        if isinstance(val, bool):
            return "yes" if val else "no"
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False, separators=(",", ":"))
        return clean_ws.sub(" ", str(val)).strip()

    # ---------- 3) Query entries ----------
    if unique_toggle:
        subq = (
            db.session.query(
                TestEntry.data["CM_serial"].as_integer().label("cm_serial"),
                db.func.max(TestEntry.timestamp).label("latest")
            )
            .filter(TestEntry.data["CM_serial"].isnot(None))
            .group_by(TestEntry.data["CM_serial"].as_integer())
            .subquery()
        )
        entries = (
            db.session.query(TestEntry)
            .join(
                subq,
                and_(
                    TestEntry.data["CM_serial"].as_integer() == subq.c.cm_serial,
                    TestEntry.timestamp == subq.c.latest
                )
            )
            .order_by(TestEntry.timestamp.desc())
            .all()
        )
    else:
        entries = TestEntry.query.order_by(TestEntry.timestamp.desc()).all()

    # ---------- 4) Write CSV ----------
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=',', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)

    headers = (
        ["Time", "User"]
        + [safe(getattr(f, "label", None) or f.name) for f in visible_fields]
        + ["File", "Test Aborted", "Reason Aborted"]
    )
    writer.writerow(headers)

    def username_for(entry):
        u = getattr(entry, "user", None)
        if u and getattr(u, "username", None):
            return u.username
        if isinstance(entry.contributors, list) and entry.contributors:
            return str(entry.contributors[-1])
        return ""

    for e in entries:
        data = e.data or {}
        row = [safe(e.timestamp), safe(username_for(e))]
        for f in visible_fields:
            row.append(safe(data.get(f.name)))
        row += [safe(e.file_name), "yes" if e.failure else "no", safe(e.fail_reason)]
        writer.writerow(row)

    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
    return send_file(
        io.BytesIO(csv_bytes),
        mimetype='text/csv',
        as_attachment=True,
        download_name='test_results.csv'
    )

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

    return render_template("dashboard.html", entries=entries, now=datetime.now(EASTERN_TZ))

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

    return render_template('failed_tests.html', entries=entries, now=datetime.now(EASTERN_TZ))

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
        timestamp=datetime.now(EASTERN_TZ),
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
    #DEBUG PRINT
    #print(f"new user you form_id: {user.form_id}")
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
