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
from random import randint, uniform, choice #for random
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask import send_from_directory
from werkzeug.utils import secure_filename
from models import db, User, TestEntry, EntrySlot





app = Flask(__name__)
app.config['SECRET_KEY'] = 'testsecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Define multiple forms, each with its own fields and a unique name

#Field: name, label, type, display_history

# need to use blank.copy() after an instance of blank if no other field comes next to it
blank = { "name": "blank", "label": "", "type": None, "display_history": False }

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
        "name": "power_test",
        "label": "Power Test",
        "fields": [
            { "name": "management_power", "label": "Management Power", "type": "float" },
            { "name": "power_supply_voltage", "label": "Power Supply Voltage (V) when 3.3 V becomes good", "type": "float" },
            { "name": "current_draw", "label": "Current Draw (mA) at 3.3 V", "type": "float" },
            { "name": "mcu_programmed", "label": "MCU Programmed Successfully", "type": "boolean" }
        ]
    },
    {
        "name": "i2c_tests",
        "label": "I2C Tests",
        #should add links to help page for each of these tests w/ explanation and link to github where tests can be found
        "fields": [
            { "name": "i2c_to_dcdc", "label": "I2C to DC-DC Converter Passed", "type": "boolean"},
            { "name": "dcdc_converter_test", "label": "All DC-DC Converters Passed", "type": "boolean"},
            { "name": "i2c_to_clockchips", "label": "Clock Chips I2C Test Passed", "type": "boolean" },
            { "name": "i2c_to_fpgas", "label": "I2C to FPGA's Passed", "type": "boolean"}, #may need to adjust if dont have fpga's on board
            { "name": "i2c_to_firefly_bank1", "label": "I2C to FireFly Bank 1 Passed", "type": "boolean"},
            { "name": "i2c_to_firefly_bank2", "label": "I2C to FireFly Bank 2 Passed", "type": "boolean"}, #"havent given much thought yet" -prod test doc
            { "name": "i2c_to_eeprom", "label": "I2C to EEPROM Passed", "type": "boolean"},
        ]
    },
    {
        "name": "second_step_mcu_test",
        "label": "Second-Step MCU Test",
        "fields": [
            { "name": "second_step_instruction", "label": "Set FireFly transmit switches to the 3.3v position and load second step code, (clock output sent through front panel connector)", "type": "null", "display_history": False },
            { "name": "fpga_oscillator_clock_1", "label": "FPGA Oscillator Clock Frequency 1 (MHz)", "type": "float" },
            { "name": "fpga_oscillator_clock_2", "label": "FPGA Oscillator Clock Frequency 2 (MHz)", "type": "float" },
            { "name": "fpga_flash_memory", "label": "FPGA Flash Memory Test", "type": "boolean"},
        ]
    },

    {
        "name": "link_test",
        "label": "Link Integrity Testing",
        "fields": [
            { "name": "fpga_second_step_tip", "label": "Load the second-step FPGA code to test FPGA-FPGA and MCU-FPGA connections", "type": "null", "display_history": False },
            { "name": "ibert_test", "label": "IBERT link Test Passed", "type": "boolean" },
            { "name": "full_link_test", "label": "Firefly, FPGA-FPGA, C2C, and TCDS Links Passed", "type": "boolean" },
        ]
    },

    {
        "name": "manual_link_testing",
        "label": "Manual Link Testing",
        "fields": [
            { "name": "manual_test_tip_1", "label": "Remove the board from the test stand. Remove the FireFly devices and loopback cables. Install the proper FireFly configuraton for the end use.", "type": "null", "display_history": False},
            blank,
            { "name": "manual_test_tip_2", "label": "Set the FireFly transmit voltage switches to 3.8v for 25Gx12 transmitters. Install the FireFly heatsink. Route FireFly cables to the front panel. Install loopback connectors", "type": "null", "display_history": False },
            blank,
            { "name": "manual_test_tip_3", "label": "Connect the CM to the golden SM. Install the SM front panel board. Attach a front panel, and connect the handle switch. Install covers. Install the board in an ATCA shelf and apply power. ", "type": "null", "display_history": False },
            blank,
            { "name": "manual_test_tip_4", "label": "Load MCU code and configure clock chips for normal operation, then load the thrid step FPGA code", "type": "null", "display_history": False },
            blank,
            { "name": "third_step_fpga_test", "label": "Thrid Step FPGA Test Passed", "type": "boolean" },
        ]
    },

    {
        "name": "heating_tests",
        "label": "Heating Testing",
        "fields": [
            { "name": "heating_test", "label": "Heater Tests Passed With Sufficent Cooling", "type": "boolean" },
            { "name": "heating_tip", "label": "Remove the CM/SM from the ATCA shelf. Remove the FireFly loopback connectors. Separate the CM from the SM. Pack the CM for shipping", "type": "null", "display_history": False },
            blank,
            blank.copy(),
        ]
    },

    #will probably need to change when look into specific tests more prob need to add to each automatic testing session
    {
        "name": "report_upload",
        "label": "Upload Test Report",
        "fields": [
            { "name": "test_report", "label": "Upload PDF", "type": "file" },
        ]
    },
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

def validate_field(field, value):
    """Validate a single field value based on its type and requirements."""
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

@app.route('/form', methods=['GET', 'POST'])
def form():
    """form data entry"""
    SERIAL_OFFSET = 3000 # to prevent wasting memory make this the first serial number so 'forms_per_serial'[0] maps to CM3000
    if 'user_id' not in session:
        return redirect(url_for('login'))

    form_index = request.args.get('step')
    if form_index is None:
        cm_serial = session.get('form_data', {}).get("CM_serial")
        if cm_serial:
            index = int(cm_serial) - SERIAL_OFFSET
            saved = session['forms_per_serial'][index]
            if saved:
                entry = EntrySlot.from_dict(saved)
                form_index = entry.data.get('last_step', 0)

    form_index = int(form_index or 0)
    form_index = max(0, min(form_index, len(FORMS) - 1))
    current_form = FORMS[form_index]

    if 'form_data' not in session:
        session['form_data'] = {}

    if 'forms_per_serial' not in session:
        session['forms_per_serial'] = [None] * 51

    if request.method == 'POST':
        # Step 1: update form_data with current inputs
        for field in current_form["fields"]:
            value = request.form.get(field["name"])
            if value is not None:
                session['form_data'][field["name"]] = value

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

            if index is not None:
                if 'timestamp' not in session['form_data']:
                    session['form_data']['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                session['forms_per_serial'][index] = EntrySlot(
                    closed=False,
                    data=session['form_data'].copy()
                ).to_dict()
                session.modified = True

            return redirect(url_for('dashboard'))

        # Step 4: full validation for Next
        is_valid, errors = validate_form(current_form["fields"], request)

        if is_valid:
            # Handle file uploads
            for field in current_form["fields"]:
                if field["type"] == "file":
                    file = request.files.get(field["name"])
                    if file and file.filename:
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        session['form_data'][field["name"]] = filename

            if index is not None:
                if 'timestamp' not in session['form_data']:
                    session['form_data']['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                session['forms_per_serial'][index] = EntrySlot(
                    closed=False,
                    data=session['form_data'].copy()
                ).to_dict()
                session.modified = True

            if form_index + 1 < len(FORMS):
                return redirect(url_for('form', step=form_index + 1))

            # Final submission
            user = db.session.get(User, session['user_id'])
            entry = TestEntry(user=user, data=session['form_data'], timestamp=datetime.now())
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
            if saved:
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
    writer.writerow(['Time', 'User'] + [f["label"] for f in all_fields] + ['File'])

    for e in entries:
        row = [e.timestamp, e.user.username]
        row += [e.data.get(f["name"]) for f in all_fields]
        row += [e.file_name]
        writer.writerow(row)

    output.seek(0)
    return send_file(io.BytesIO(output.read().encode()), mimetype='text/csv',
                     as_attachment=True, download_name='test_results.csv')

@app.route('/help')
def help_button():
    """Bring up static help page."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return send_from_directory("static", "Apollo_CMv3_Production_Testing_04Nov2024.html")

def determine_step_from_data(data):
    for i, fo in enumerate(FORMS):
        for field in fo['fields']:
            if not data.get(field['name']):
                return i  # First incomplete step
    return len(FORMS) - 1  # Default to final step

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    SERIAL_OFFSET = 3000
    saved_entries = []
    user_forms = session.get('forms_per_serial', [])

    for index, entry_data in enumerate(user_forms):
        if entry_data:
            cm_serial = SERIAL_OFFSET + index
            entry = EntrySlot.from_dict(entry_data)
            data = entry.data
            timestamp = data.get('timestamp', 'Unknown')
            step = data.get('last_step', determine_step_from_data(data))
            step_label = FORMS[step]["label"]
            saved_entries.append({
                'cm_serial': cm_serial,
                'step': step,
                'step_label': step_label,
                'timestamp': timestamp
            })

    return render_template('dashboard.html', entries=saved_entries)

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
    """adds dummy entires activate with:
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
        test_data = {
            "CM_serial": randint(3000, 3050),
            "passed_visual": choice([True, False]),
            "comments": "Auto-generated entry",
            "management_power": round(uniform(2.5, 3.3), 2),
            "power_supply_voltage": round(uniform(3.2, 3.5), 2),
            "current_draw": round(uniform(200, 400), 1),
            "resistance": round(uniform(1.0, 10.0), 2),
            "mcu_programmed": choice([True, False]),
            "i2c_to_dcdc": choice([True, False]),
            "dcdc_converter_test": choice([True, False]),
            "i2c_to_clockchips": choice([True, False]),
            "i2c_to_fpgas": choice([True, False]),
            "i2c_to_firefly_bank": choice([True, False]),
            "i2c_to_eeprom": choice([True, False]),
            "fpga_oscillator_clock_1": round(uniform(100.0, 150.0), 2),
            "fpga_oscillator_clock_2": round(uniform(100.0, 150.0), 2),
            "fpga_flash_memory": choice([True, False]),
            "ibert_test": choice([True, False]),
            "full_link_test": choice([True, False]),
            "third_step_fpga_test": choice([True, False]),
            "heating_test": choice([True, False])
        }

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
                if field["type"] == "boolean":
                    entry_data[field["name"]] = choice(["yes", "no"])
                elif field["type"] == "integer":
                    entry_data[field["name"]] = str(randint(0, 1000))
                elif field["type"] == "float":
                    entry_data[field["name"]] = f"{uniform(0, 10):.2f}"
                elif field["type"] == "text":
                    entry_data[field["name"]] = "Lorem ipsum"

        # Determine last step with missing fields
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

def get_current_user():
    """Returns the current logged-in User object, or None if not logged in"""
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return db.session.get(User, user_id)

def authenticate_admin():
    """Returns True if current user is admin, False otherwise.
    Logs non-admin or unauthenticated users to fishy_users."""
    user = get_current_user()
    if user is None or user.get_username() != "admin":
        username = user.get_username() if user else "anonymous"
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
