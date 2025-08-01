"""
admin_routes.py

Defines all administrative routes for managing users, test data, and system state
in the Flask web application. These routes are restricted to authenticated admin users.

Features:
- User Management:
    - /create_admin: Create a new admin user.
    - /promote_user: Promote an existing user to admin status.
    - /demote_user: Demote an admin user to regular status.
    - /list_fishy_users: View users flagged for suspicious admin access attempts.

- Admin Help:
    - /admin/help: View a list of available admin commands and their descriptions.

- Data Generation and Testing:
    - /add_dummy_entry: Generate dummy test entries for testing the form pipeline.
    - /add_dummy_saves: Generate dummy in-progress form saves (session-based).
    - /check_dummy_count: Count the number of dummy (test=True) entries in the database.

- Data Clearing and Cleanup:
    - /clear_history: Delete all test history and uploaded files.
    - /clear_dummy_history: Delete only dummy (test=True) entries and associated files.
    - /clear_saves: Clear all saved form progress for the current user.
    - /clear_dummy_saves: Clear only dummy saves for the current user.

- Admin Dashboard Actions:
    - /admin/admin_dashboard: View all in-progress TestEntry forms.
    - /admin/clear_lock/<entry_id>: Remove a lock from a TestEntry.
    - /admin/delete_form/<entry_id>: Delete a TestEntry and archive it in DeletedEntry.
    - /admin/deleted_entries: View all deleted/archived entries for audit or recovery.

Security:
All routes require:
- A valid user session (via `session['user_id']`)
- Admin status (checked using `authenticate_admin()`)

Note:
Dummy data and cleanup routes are intended for development/debugging and may be disabled
or removed in production environments.
"""

import os
from datetime import datetime
from random import randint, uniform, choice
from flask import render_template, request, redirect, url_for, session, current_app, Blueprint

from models import db, TestEntry, EntrySlot, DeletedEntry, User
from form_config import FORMS_NON_DICT
from utils import (current_user, authenticate_admin)
from constants import SERIAL_OFFSET, SERIAL_MIN, SERIAL_MAX

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

fishy_users = {}

## Admin commands for managing admin's debugging and generating test data

@admin_bp.route('/create_admin', methods=['GET', 'POST'])
def create_admin():
    """
    Creates a new user account with administrator privileges.
    Uses the standard registration form but elevates privileges.
    """

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            return "User already exists."

        new_admin = User(username=username, administrator=True)
        new_admin.set_password(password)  # This will hash the SHA-256 hash again
        db.session.add(new_admin)
        db.session.commit()

        return f"Admin user {username} created successfully."

    return render_template('register.html', is_admin_creation=True)

@admin_bp.route('/promote_user', methods=['GET', 'POST'])
def promote_user():
    """
    Promotes an existing user to admin status.

    Accessible only to logged-in admin users. Displays a form to input a username.
    On POST, sets the `administrator` flag of the specified user to True if not already an admin.

    Need to disable authenticate_admin check upon creation of new users.db without any exsiting admins
    """

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    if request.method == 'POST':
        username = request.form['username']
        user = User.query.filter_by(username=username).first()

        if not user:
            return f"No such user: {username}"

        if user.administrator:
            return f"User {username} is already an admin."

        user.administrator = True
        db.session.commit()
        return f"User {username} promoted to admin."

    return '''
        <form method="post">
            Username to promote: <input type="text" name="username"><br>
            <input type="submit" value="Promote to Admin">
        </form>
    '''

@admin_bp.route('/demote_user', methods=['GET', 'POST'])
def demote_user():
    """
    Demotes an existing user by removing admin privileges.

    Accessible only to logged-in admin users. Displays a form to enter a username,
    and on POST, updates the specified user's `administrator` flag to False.
    """

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    if request.method == 'POST':
        username = request.form['username']

        user = User.query.filter_by(username=username).first()

        if not user:
            return f"No such user: {username}"

        if not user.administrator:
            return f"User {username} is already not an admin."

        user.administrator = False
        db.session.commit()
        return f"User {username} demoted from admin."

    return '''
        <form method="post">
            Username to demote: <input type="text" name="username"><br>
            <input type="submit" value="Remove Admin Privileges">
        </form>
    '''

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

@admin_bp.route('/help')
def list_admin_commands():
    """
    Displays a list of all admin routes and their descriptions.
    """

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    # commented commands are not needed

    commands = {
        '/admin/create_admin': 'Create a new admin user.',
        '/admin/promote_user': 'Promote an existing user to admin.',
        '/admin/demote_user': 'Demote an admin to a regular user.',
        '/admin/users': 'List all users, promote/demote or delete them.',
        '/admin/forms/': 'View and edit form fields, pages, and help page entries.',
        '/admin/forms/help': 'View help documentation for form editing.',
        '/admin/list_fishy_users': 'View users flagged for suspicious admin access attempts.',
        '/admin/add_dummy_entry?count=#': 'Add dummy test entries to the database.',
        #'/admin/clear_history': 'Delete all test history and uploaded files.',
        '/admin/clear_dummy_history': 'Delete only test=True (dummy) history entries and files.',
        '/admin/check_dummy_count': 'Show the number of dummy entries in the database.',
        '/admin/admin_dashboard': 'Admin dashboard for viewing in-progress forms.',
        #'/admin/clear_lock/<entry_id>': 'Clear the lock on a form so it can be edited.',
        #'/admin/delete_form/<entry_id>': 'Delete a form and archive it in DeletedEntry.',
        '/admin/deleted_entries': 'View forms that have been deleted from the dashboard.',
    }

    return render_template('admin/admin_commands.html', commands=commands)


# data generation commands - old as of 7/21 - not necessasary for time being

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

    user = current_user()

    for _ in range(count):
        test_data = {}

        for form_iter in FORMS_NON_DICT:
            for field in form_iter.fields:
                name = getattr(field, "name", None)
                ftype = getattr(field, "type_field", None)

                if not name or ftype is None:
                    continue

                if ftype == "boolean":
                    test_data[name] = choice(["yes", "no"])
                elif ftype == "integer":
                    test_data[name] = str(randint(SERIAL_MIN, SERIAL_MAX)) if name == "CM_serial" else str(randint(0, 9999))
                elif ftype == "float":
                    test_data[name] = f"{uniform(0.0, 10.0):.2f}"
                elif ftype == "text":
                    test_data[name] = "Auto-generated entry"
                elif ftype == "file":
                    test_data[name] = ""  # Leave blank for file fields

        entry = TestEntry(
            contributors=[user.username],
            data=test_data,
            timestamp=datetime.utcnow(),
            test=True
        )
        db.session.add(entry)

    db.session.commit()
    return redirect(url_for('history'))

@admin_bp.route('/clear_history')
def clear_history():
    '''clears all entries from history to be TODO removed later (same as clear_dummy_history now)'''
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"
    with current_app.app_context():
        #db.session.query(TestEntry).delete() # uncomment this line to delete all history entries keep disabled for actual web app run
        db.session.query(TestEntry).filter_by(test=True).delete() # is now the same method as 'clear_dummy_history' - editing history is not allowed on full release
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

# for admin dashboard:
@admin_bp.route('/admin_dashboard')
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

    return render_template("admin/admin_dashboard.html", forms=forms)

@admin_bp.route('/clear_lock/<int:entry_id>', methods=['POST'])
def clear_lock(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    entry = TestEntry.query.get(entry_id)
    if entry and entry.lock_owner:
        entry.lock_owner = None
        db.session.commit()

    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/delete_form/<int:entry_id>', methods=['POST'])
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

    return redirect(url_for('admin.admin_dashboard'))

# for admin view of deleted entries:

@admin_bp.route('/deleted_entries')
def deleted_entries():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    entries = DeletedEntry.query.order_by(DeletedEntry.deleted_at.desc()).all()
    return render_template('admin/deleted_entries.html', entries=entries)

@admin_bp.route('/users', methods=['GET', 'POST'])
def list_users():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        return "Permission Denied"

    if request.method == 'POST':
        action = request.form.get('action')
        user_id = int(request.form.get('user_id'))
        user = User.query.get(user_id)

        if not user:
            return f"User ID {user_id} not found.", 404

        if action == 'promote':
            user.administrator = True
        elif action == 'demote':
            user.administrator = False
        elif action == 'delete':
            db.session.delete(user)

        db.session.commit()
        return redirect(url_for('admin.list_users'))

    users = User.query.all()
    return render_template('admin/manage_users.html', users=users)
