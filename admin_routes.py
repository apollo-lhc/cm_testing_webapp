import os
from datetime import datetime
from random import randint, uniform, choice
from flask import render_template, request, redirect, url_for, session, current_app, Blueprint

from models import db, TestEntry, EntrySlot, DeletedEntry
from form_config import FORMS
from utils import (
    current_user,
    authenticate_admin
)



admin_bp = Blueprint('admin', __name__)

fishy_users = {}

## Admin commands for debugging and generating test data

@admin_bp.route('/list_fishy_users')
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

@admin_bp.route('/add_dummy_entry')
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

@admin_bp.route('/add_dummy_saves')
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

@admin_bp.route('/clear_history')
def clear_history():
    '''clears all entries from history to be removed later'''
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    with current_app.app_context():
        db.session.query(TestEntry).delete()
        db.session.commit()

        upload_dir = current_app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                os.remove(file_path)
            except Exception:
                pass  # Silently ignore errors

    return redirect(request.referrer or url_for('history'))

@admin_bp.route('/clear_dummy_history')
def clear_dummy_history():
    """clears only entries with test=True from history"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    with current_app.app_context():
        db.session.query(TestEntry).filter_by(test=True).delete()
        db.session.commit()


        upload_dir = current_app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                os.remove(file_path)
            except Exception:
                pass  # Silently ignore errors

    return redirect(request.referrer or url_for('history'))

@admin_bp.route('/check_dummy_count')
def check_dummy_count():
    """returns number of dummy entires in history"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    count = db.session.query(TestEntry).filter_by(test=True).count()
    return f"Dummy entries: {count}"

@admin_bp.route('/clear_saves')
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

@admin_bp.route('/clear_dummy_saves')
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

@admin_bp.route('/admin/admin_dashboard')
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

@admin_bp.route('/admin/clear_lock/<int:entry_id>', methods=['POST'])
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

@admin_bp.route('/admin/delete_form/<int:entry_id>', methods=['POST'])
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

@admin_bp.route('/admin/deleted_entries')
def deleted_entries():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    entries = DeletedEntry.query.order_by(DeletedEntry.deleted_at.desc()).all()
    return render_template('deleted_entries.html', entries=entries)
