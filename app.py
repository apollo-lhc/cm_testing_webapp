"""
Flask web application for managing test entries with user authentication.

Features:
- User registration and login
- Form submission for test data with file upload
- History view of all test entries
- CSV export of test results
- File download for uploaded reports
"""

import os
import io
import csv
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask import send_from_directory
from werkzeug.utils import secure_filename
from models import db, User, TestEntry

app = Flask(__name__)
app.config['SECRET_KEY'] = 'testsecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Define multiple forms, each with its own fields and a unique name
FORMS = [
    {
        "name": "hardware_test",
        "label": "Hardware Test",
        "fields": [
            {
                "name": "CM_serial",
                "label": "CM Serial number",
                "type": "integer",
                # Custom validation: must be in range 3000-3050
                "validate": lambda v: (3000 <= int(v) <= 3050, "Must be between 3000 and 3050") if v and v.isdigit() else (False, "Must be an integer between 3000 and 3050")
            },
            { "name": "passed_visual", "label": "Passed Visual Inspection", "type": "boolean" },
            { "name": "comments", "label": "Comments", "type": "text" },
        ]
    },
    {
        "name": "electrical_test",
        "label": "Electrical Test",
        "fields": [
            { "name": "mcu_test_program", "label": "MCU test program", "type": "boolean" },
            { "name": "current_draw", "label": "Current Draw (mA)", "type": "float" },
            { "name": "voltage", "label": "Voltage (V)", "type": "float" },
            { "name": "resistance", "label": "Resistance (Ohms)", "type": "float" },
        ]
    },
    {
        "name": "report_upload",
        "label": "Upload Test Report",
        "fields": [
            { "name": "test_report", "label": "Upload PDF", "type": "file" },
        ]
    }
]

db.init_app(app)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin')  # type: ignore
        admin.set_password('password')
        db.session.add(admin)
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
            return 'User already exists'
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
            return redirect(url_for('index'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    """logout route"""
    session.pop('user_id', None)
    return redirect(url_for('login'))

def validate_field(field, value):
    """Validate a single field value based on its type and requirements."""
    # Per-field custom validation
    if "validate" in field and callable(field["validate"]):
        valid, msg = field["validate"](value)
        if not valid:
            print(f"Validation failed for {field['name']}: {msg} (value={value})")
            return False, msg

    if field["type"] == "integer":
        if value is None or value == "":
            return False, "This field is required."
        try:
            int(value)
        except ValueError:
            return False, "Must be an integer."
    elif field["type"] == "float":
        if value is None or value == "":
            return False, "This field is required."
        try:
            float(value)
        except ValueError:
            return False, "Must be a number."
    elif field["type"] == "boolean":
        if value not in ("yes", "no"):
            return False, "Please select yes or no."
    elif field["type"] == "file":
        if not value:
            return False, "File is required."
    # Add more types as needed
    return True, ""

def validate_form(fields, req):
    """Validate all fields in the form. Returns (is_valid, errors_dict)."""
    errors = {}
    for field in fields:
        if field["type"] == "file":
            file = req.files.get(field["name"])
            value = file.filename if file and file.filename else None
        else:
            value = req.form.get(field["name"])
        valid, msg = validate_field(field, value)
        if not valid:
            errors[field["name"]] = msg
    return (len(errors) == 0), errors

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main page with sequential forms for test entries"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Track current form index in session
    if 'form_index' not in session:
        session['form_index'] = 0
        session['form_data'] = {}
        session['file_name'] = None

    form_index = session['form_index']
    if form_index >= len(FORMS):
        # All forms completed
        # Save the entry and reset session progress
        entry = TestEntry(
            user_id=session['user_id'], # type: ignore
            data=session['form_data'], # type: ignore
            file_name=session.get('file_name') # type: ignore
        )
        db.session.add(entry)
        db.session.commit()
        session.pop('form_index')
        session.pop('form_data')
        session.pop('file_name', None)
        return render_template("form_complete.html")

    current_form = FORMS[form_index]
    fields = current_form["fields"]

    errors = {}

    if request.method == 'POST':
        is_valid, errors = validate_form(fields, request)
        if is_valid:
            # Collect data for the current form
            for field in fields:
                if field["type"] == "file":
                    file = request.files.get(field["name"])
                    if file and file.filename:
                        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                        filename = f"{timestamp}_{secure_filename(file.filename)}"
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        session['file_name'] = filename
                elif field["type"] == "boolean":
                    session['form_data'][field["name"]] = request.form.get(field["name"]) == "yes"
                elif field["type"] == "float":
                    val = request.form.get(field["name"])
                    session['form_data'][field["name"]] = float(val) if val else None
                elif field["type"] == "integer":
                    val = request.form.get(field["name"])
                    session['form_data'][field["name"]] = int(val) if val else None
                else:
                    session['form_data'][field["name"]] = request.form.get(field["name"])
            # Move to next form
            session['form_index'] = form_index + 1
            return redirect(url_for('index'))
        # else: fall through to re-render form with errors

    return render_template(
        "form.html",
        fields=fields,
        form_label=current_form["label"],
        form_index=form_index,
        total_forms=len(FORMS),
        errors=errors
    )

@app.route('/restart_forms')
def restart_forms():
    """Restart the multi-form entry process."""
    session.pop('form_index', None)
    session.pop('form_data', None)
    session.pop('file_name', None)
    return redirect(url_for('index'))

@app.route('/history')
def history():
    """Show history of all test entries."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    entries = TestEntry.query.order_by(TestEntry.timestamp.desc()).all()
    # Use all fields from all FORMS for history display
    all_fields = []
    for form in FORMS:
        all_fields.extend(form["fields"])
    return render_template('history.html', entries=entries, fields=all_fields)

@app.route('/export_csv')
def export_csv():
    """Export all test entries to CSV."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    output = io.StringIO()
    writer = csv.writer(output)
    # Combine all fields from all forms for CSV export
    all_fields = []
    for form in FORMS:
        all_fields.extend(form["fields"])
    writer.writerow(['Time', 'User'] + [f["label"] for f in all_fields] + ['File'])
    entries = TestEntry.query.all()
    for e in entries:
        row = [e.timestamp, e.user.username]
        row += [e.data.get(f["name"]) for f in all_fields]
        row += [e.file_name]
        writer.writerow(row)
    output.seek(0)
    return send_file(io.BytesIO(output.read().encode()), mimetype='text/csv',
                     as_attachment=True, download_name='test_results.csv')

@app.route('/unique_cm_serials')
def unique_cm_serials():
    """Show one entry per unique CM_serial (latest by timestamp)."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    entries = TestEntry.query.order_by(TestEntry.timestamp.desc()).all()
    all_fields = []
    for form in FORMS:
        all_fields.extend(form["fields"])
    # Find the field name for CM_serial
    cm_serial_field = next((f["name"] for f in all_fields if f["name"].lower() == "cm_serial"), None)
    if not cm_serial_field:
        return "CM_serial field not found.", 500

    seen = set()
    unique_entries = []
    for entry in entries:
        cm_serial = entry.data.get(cm_serial_field)
        if cm_serial not in seen:
            seen.add(cm_serial)
            unique_entries.append(entry)
    return render_template('unique_cm_serials.html', entries=unique_entries, fields=all_fields)

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    app.run(port=5001, debug=True, host='0.0.0.0')
