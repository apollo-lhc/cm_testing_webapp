"""
Database models for the test entry application.

Includes:
- User: authentication and password management
- TestEntry: stores test data, file uploads, and user association
- EntrySlot: need to add writeup when finished with it
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.sqlite import JSON

db = SQLAlchemy()

class User(db.Model):
    """User model for authentication."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    administrator = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        """Hash and set the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check the user's password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def get_username(self):
        """returns username for logging purposes"""
        return self.username

class TestEntry(db.Model):
    """Model for storing test entry data and file uploads."""

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow) # used on submission and failure and save, timestamp shown in history table summary
    #TODO add current timestamp for in progress forms
    #user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    data = db.Column(JSON)
    file_name = db.Column(db.String(120))
    #user = db.relationship('User', backref=db.backref('entries', lazy=True))
    test = db.Column(db.Boolean, default=False)
    failure = db.Column(db.Boolean, default=False)
    fail_reason = db.Column(db.String, default=None)

    fail_stored = db.Column(db.Boolean, default=False)

# -------------- NEW GLOBAL‑SAVE FIELDS --------------
    is_saved         = db.Column(db.Boolean, default=False)
    is_finished = db.Column(db.Boolean, default=False)
    contributors     = db.Column(JSON, default=list)                  # e.g. ["alice","bob"]
    lock_owner       = db.Column(db.String(80), nullable=True)
    lock_acquired_at = db.Column(db.DateTime, nullable=True)
    # ----------------------------------------------------

class EntryHistory(db.Model):
    #need to implement in save and exit logic
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('test_entry.id'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    form_index = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    creation_time = db.Column(db.DateTime, nullable=True)
    changes = db.Column(JSON)  # Optional: record diff or snapshot of fields

class DeletedEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_entry_id = db.Column(db.Integer)   # id of the TestEntry that was deleted
    deleted_by = db.Column(db.String(80))       # username of admin who deleted
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)

    data = db.Column(JSON)                      # copy of the TestEntry data
    contributors = db.Column(db.PickleType)     # list of contributors
    fail_reason = db.Column(db.Text)
    failure = db.Column(db.Boolean)
    was_locked = db.Column(db.String(80))       # lock owner, if an


class EntrySlot:
    """Model for keeping track and saving in use forms per serial number"""
    def __init__(self, closed=False, data=None, test=False):
        self.closed = closed
        self.data = data or {}
        self.test = test

    def to_dict(self):
        return {
            'closed': self.closed,
            'data': self.data,
            'test': self.test
        }

    @staticmethod
    def from_dict(d):
        return EntrySlot(
            closed=d.get('closed', False),
            data=d.get('data', {}),
            test=d.get('test', False)
        )

class FormField:
    def __init__(
        self,
        *,
        name=None,
        label=None,
        type_field=None,
        validate=None,
        display_history=True,
        display_form=True,
        help_text=None,
        help_link=None,
        help_label=None,
        help_target=None,
    ):
        self.name = name
        self.label = label
        self.type_field = type_field
        self.validate = validate
        self.display_history = display_history
        self.display_form = display_form
        if not self.display_form:
            self.display_history = False
        self.help_text = help_text
        self.help_link = help_link
        self.help_label = help_label
        self.help_target = help_target

    def __repr__(self):
        return f"FormField(name={self.name}, label={self.label}, type_field={self.type_field})"

    @classmethod
    def blank(cls):
        return cls(name="blank", label="", type_field=None, display_history=False)

    @classmethod
    def null(cls, *, name, label, help_text=None, help_link=None, help_label=None, help_target=None):
        return cls(
            name=name,
            label=label,
            type_field="null",
            display_history=False,
            help_text=help_text,
            help_link=help_link,
            help_label=help_label,
            help_target=help_target
        )

    @classmethod
    def help_instance(cls, *, name, help_text=None, help_link=None, help_label=None):
        return cls(
            name=name,
            display_form=False,
            display_history=False,
            help_text=help_text,
            help_link=help_link,
            help_label=help_label,
        )

    @classmethod
    def text(cls, *, name, label, validate=None, display_history=True, help_text=None, help_link=None, help_label=None, help_target=None):
        return cls(
            name=name,
            label=label,
            type_field="text",
            validate=validate,
            display_history=display_history,
            help_text=help_text,
            help_link=help_link,
            help_label=help_label,
            help_target=help_target
        )

    @classmethod
    def integer(cls, *, name, label, validate=None, display_history=True, help_text=None, help_link=None, help_label=None, help_target=None):
        return cls(
            name=name,
            label=label,
            type_field="integer",
            validate=validate,
            display_history=display_history,
            help_text=help_text,
            help_link=help_link,
            help_label=help_label,
            help_target=help_target
        )

    @classmethod
    def float(cls, *, name, label, validate=None, display_history=True, help_text=None, help_link=None, help_label=None, help_target=None):
        return cls(
            name=name,
            label=label,
            type_field="float",
            validate=validate,
            display_history=display_history,
            help_text=help_text,
            help_link=help_link,
            help_label=help_label,
            help_target=help_target
        )

    @classmethod
    def boolean(cls, *, name, label, validate=None, display_history=True, help_text=None, help_link=None, help_label=None, help_target=None):
        return cls(
            name=name,
            label=label,
            type_field="boolean",
            validate=validate,
            display_history=display_history,
            help_text=help_text,
            help_link=help_link,
            help_label=help_label,
            help_target=help_target
        )

    @classmethod
    def file(cls, *, name, label, validate=None, display_history=True, help_text=None, help_link=None, help_label=None, help_target=None):
        return cls(
            name=name,
            label=label,
            type_field="file",
            validate=validate,
            display_history=display_history,
            help_text=help_text,
            help_link=help_link,
            help_label=help_label,
            help_target=help_target
        )
    def get_value(self, request):
        if self.type_field == "file":
            file = request.files.get(self.name)
            return file.filename if file and file.filename else None
        return request.form.get(self.name)

    def validate_value(self, value, existing_data=None):
        if self.validate:
            return self.validate(value)
        if self.type_field in ("integer", "float"):
            if value is None or value == "":
                return False, "This field is required."
            try:
                float(value) if self.type_field == "float" else int(value)
            except ValueError:
                return False, f"Must be a {self.type_field}."
        elif self.type_field == "boolean":
            if value not in ("yes", "no"):
                return False, "Please select yes or no."
        elif self.type_field == "file":
            if not value and not (existing_data or {}).get(self.name):
                return False, "File is required."
        return True, ""
