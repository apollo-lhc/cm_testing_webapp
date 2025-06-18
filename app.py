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

#for random:
from random import randint, uniform, choice


from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask import send_from_directory
from werkzeug.utils import secure_filename
from models import db, User, TestEntry






app = Flask(__name__)
app.config['SECRET_KEY'] = 'testsecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Define multiple forms, each with its own fields and a unique name

#Field: name, label, type, display_history

# need to use blank.copy() after an instance of blank if no other field comes next to it
blank = { "name": "blank", "label": "", "type": None, "display_history": False }

#change with the lambda expression
latest_cm_entries = [None] * 51


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
            { "name": "resistance", "label": "Resistance (Ohms)", "type": "float" },
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
            { "name": "i2c_to_firefly_bank", "label": "I2C to FireFly Bank Passed", "type": "boolean"},
            { "name": "i2c_to_eeprom", "label": "I2C to EEPROM Passed", "type": "boolean"},
            #{ "name": "i2c_to_firefly_bank", "label": "I2C to FireFly Bank passed", "type": "boolean"}, #"havent given much thought yet" -prod test doc
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





@app.route('/add_dummy_entry')
def add_dummy_entry():
    """adds dummy entires activate with:
    http://localhost:5001/add_dummy_entry → adds 1 entry
    http://localhost:5001/add_dummy_entry?count=10 → adds 10 entries"""

    if 'user_id' not in session:
        return redirect(url_for('login'))

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
            timestamp=datetime.utcnow()
        )

        db.session.add(entry)
        update_latest_cm_entry(entry)

    db.session.commit()
    return redirect(url_for('history'))


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

@app.route('/form', methods=['GET', 'POST'])
def form():
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
        update_latest_cm_entry(entry)
        session.pop('form_index')
        session.pop('form_data')
        session.pop('file_name', None)
        return render_template("form_complete.html")

    current_form = FORMS[form_index]
    fields = current_form["fields"]

    errors = {}
    prefill_values = {}

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
            return redirect(url_for('form'))
        # if error store previous values to refil form when displayed with errors
        for field in fields:
            if field["type"] == "file":
                continue
            prefill_values[field["name"]] = request.form.get(field["name"])
    else:
        for field in fields:
            prefill_values[field["name"]] = session['form_data'].get(field["name"], "")

    return render_template(
        "form.html",
        fields=fields,
        form_label=current_form["label"],
        form_index=form_index,
        total_forms=len(FORMS),
        errors=errors,
        prefill_values=prefill_values
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

    # Use all fields from all FORMS for history display
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
    output = io.StringIO()
    writer = csv.writer(output)
    # Combine all fields from all forms for CSV export
    all_fields = []
    for single_form in FORMS:
        all_fields.extend(single_form["fields"])
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

# @app.route('/unique_cm_serials')
# def unique_cm_serials():
#     """Show one entry per unique CM_serial (latest by timestamp)."""
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
#     entries = TestEntry.query.order_by(TestEntry.timestamp.desc()).all()
#     all_fields = []
#     for single_form in FORMS:
#         all_fields.extend(single_form["fields"])
#     # Find the field name for CM_serial
#     cm_serial_field = next((f["name"] for f in all_fields if f["name"].lower() == "cm_serial"), None)
#     if not cm_serial_field:
#         return "CM_serial field not found.", 500

#     seen = set()
#     unique_entries = []
#     for entry in entries:
#         cm_serial = entry.data.get(cm_serial_field)
#         if cm_serial not in seen:
#             seen.add(cm_serial)
#             unique_entries.append(entry)
#     return render_template('unique_cm_serials.html', entries=unique_entries, fields=all_fields)

@app.route('/help')
def help_button():
    """Bring up static help page."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return send_from_directory("static", "Apollo_CMv3_Production_Testing_04Nov2024.html")

def update_latest_cm_entry(entry):
    cm_serial = entry.data.get("CM_serial")
    if cm_serial is None:
        return
    user = db.session.query(User).get(entry.user_id)
    latest_cm_entries[int(cm_serial) - 3000] = {
        "timestamp": entry.timestamp,
        "username": user.username,
        "data": entry.data,
        "file_name": entry.file_name
    }


if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    app.run(port=5001, debug=True, host='0.0.0.0')
