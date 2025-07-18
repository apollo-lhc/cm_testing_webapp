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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    data = db.Column(JSON)
    file_name = db.Column(db.String(120))
    user = db.relationship('User', backref=db.backref('entries', lazy=True))
    test = db.Column(db.Boolean, default=False)
    failure = db.Column(db.Boolean, default=False)
    fail_reason = db.Column(db.String, default=None)

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
