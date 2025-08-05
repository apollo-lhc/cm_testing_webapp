"""
Admin Form Editor Routes for Apollo CM Test Entry Application.

This module provides administrative functionality for editing, previewing, and managing
multi-step form definitions used in test data entry. These routes are restricted to admin users
and allow dynamic editing of form structure without modifying backend code.

Features:
- List all form pages and fields
- Add, delete, or reorder form pages
- Add, delete, or reorder individual fields on any page (except Page 0)
- Edit field properties such as label, name, type, help text, and visibility options
- Preview any form page with dummy data
- Download the current `forms_config.json` for backup or inspection
- Reset the form configuration to its default state
- View help documentation for editing form structure

Blueprint:
- URL Prefix: `/admin/forms`
- Blueprint name: `form_editor`

Dependencies:
- `FORMS_NON_DICT`: The in-memory list of `FormPage` objects used for dynamic form rendering
- `FormField` and `FormPage`: Classes representing individual form components
- `save_forms_to_file()`: Persists changes to `forms_config.json`
- `reset_forms()`: Reloads the default form configuration from disk

Typical usage:
- Used in the Admin UI to maintain and customize the multi-step form process.
"""


import os
from flask import Blueprint, render_template, request, redirect, url_for, send_from_directory, current_app, session, flash
from form_config import FORMS_NON_DICT, save_forms_to_file, reset_forms
from models import FormField, FormPage
from utils import authenticate_admin

form_editor_bp = Blueprint("form_editor", __name__, url_prefix="/admin/forms")

@form_editor_bp.route("/")
def list_forms():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    return render_template("admin/form_editor.html", forms=FORMS_NON_DICT)

@form_editor_bp.route("/edit/<int:page_idx>/<int:field_idx>", methods=["GET", "POST"])
def edit_field(page_idx, field_idx):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))


    if page_idx == 0:
        return "Editing Page 0 is restricted.", 403

    page = FORMS_NON_DICT[page_idx]
    field = page.fields[field_idx]

    if request.method == "POST":
        field.label = request.form["label"]
        field.name = request.form["name"]
        field.type_field = request.form["type"]
        field.help_text = request.form.get("help_text")
        field.help_label = request.form.get("help_label")
        field.help_link = request.form.get("help_link")
        field.help_target = request.form.get("help_target")
        field.display_form = "display_form" in request.form
        field.display_history = "display_history" in request.form
        save_forms_to_file(FORMS_NON_DICT)
        return redirect(url_for("form_editor.list_forms", page_idx=page_idx, field_idx=field_idx))

    # Update type_field if changed in dropdown and form resubmitted
    new_type = request.args.get("type")
    if new_type:
        field.type_field = new_type

    return render_template("admin/edit_field.html", field=field, page_idx=page_idx, field_idx=field_idx)

@form_editor_bp.route("/add_field/<int:page_idx>", methods=["POST"])
def add_field(page_idx):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    if page_idx == 0:
        return "Cannot add fields to Page 0.", 403

    new_field = FormField.text(name="new_field", label="New Field")
    FORMS_NON_DICT[page_idx].fields.append(new_field)
    save_forms_to_file(FORMS_NON_DICT)
    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/delete_field/<int:page_idx>/<int:field_idx>", methods=["POST"])
def delete_field(page_idx, field_idx):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))


    if page_idx == 0:
        return "Cannot delete fields from Page 0.", 403

    if 0 <= page_idx < len(FORMS_NON_DICT):
        fields = FORMS_NON_DICT[page_idx].fields
        if 0 <= field_idx < len(fields):
            del fields[field_idx]
            save_forms_to_file(FORMS_NON_DICT)
    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/add_page", methods=["POST"])
def add_page():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    name = request.form.get("page_name")
    label = request.form.get("page_label")

    if not name or not label:
        return "Both page name and label are required.", 400

    new_page = FormPage(name=name, label=label, fields=[])
    FORMS_NON_DICT.append(new_page)
    save_forms_to_file(FORMS_NON_DICT)
    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/delete_page/<int:page_idx>", methods=["POST"])
def delete_page(page_idx):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    if page_idx == 0:
        return "Cannot delete Page 0.", 403

    if 0 <= page_idx < len(FORMS_NON_DICT):
        del FORMS_NON_DICT[page_idx]
        save_forms_to_file(FORMS_NON_DICT)

    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/move_page/<int:page_idx>/<string:direction>", methods=["POST"])
def move_page(page_idx, direction):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    if direction == "up" and page_idx > 1:
        FORMS_NON_DICT[page_idx - 1], FORMS_NON_DICT[page_idx] = (
            FORMS_NON_DICT[page_idx],
            FORMS_NON_DICT[page_idx - 1],
        )
    elif direction == "down" and page_idx < len(FORMS_NON_DICT) - 1:
        FORMS_NON_DICT[page_idx + 1], FORMS_NON_DICT[page_idx] = (
            FORMS_NON_DICT[page_idx],
            FORMS_NON_DICT[page_idx + 1],
        )
    save_forms_to_file(FORMS_NON_DICT)
    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/move_field/<int:page_idx>/<int:field_idx>/<string:direction>", methods=["POST"])
def move_field(page_idx, field_idx, direction):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    page = FORMS_NON_DICT[page_idx]
    fields = page.fields

    if direction == "up" and field_idx > 0:
        fields[field_idx - 1], fields[field_idx] = fields[field_idx], fields[field_idx - 1]
    elif direction == "down" and field_idx < len(fields) - 1:
        fields[field_idx + 1], fields[field_idx] = fields[field_idx], fields[field_idx + 1]

    save_forms_to_file(FORMS_NON_DICT)
    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/preview/<int:page_idx>")
def preview_page(page_idx):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    if not 0 <= page_idx < len(FORMS_NON_DICT):
        return "Invalid page index", 404

    page = FORMS_NON_DICT[page_idx]
    dummy_prefill = {field.name: "" for field in page.fields}

    return render_template(
        "admin/form_preview.html",
        fields=page.fields,
        form_label=f"(Preview) {page.label}",
        prefill_values=dummy_prefill,
        errors={},
        show_overwrite_prompt=False,
        trigger_fail_prompt=False,
        name=page.name
    )

@form_editor_bp.route("/reset_forms", methods=["POST"])
def reset_forms_route():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    reset_forms()
    return render_template("admin/form_editor.html", forms=FORMS_NON_DICT)

@form_editor_bp.route("/help")
def help_page():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))


    return render_template("admin/form_help.html", forms=FORMS_NON_DICT)

@form_editor_bp.route("/download_config")
def download_form_config():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    file_dir = os.path.join(current_app.root_path, "data")
    filename = "forms_config.json"
    return send_from_directory(file_dir, filename, as_attachment=True)

@form_editor_bp.route("/rename_page/<int:page_idx>", methods=["POST"])
def rename_page(page_idx):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not authenticate_admin():
        flash("Permission denied", "error")
        return redirect(url_for('home'))

    if not 0 <= page_idx < len(FORMS_NON_DICT):
        return "Invalid page index", 400

    new_name = request.form.get("new_page_name", "").strip()
    new_label = request.form.get("new_page_label", "").strip()

    if new_name and new_label:
        FORMS_NON_DICT[page_idx].name = new_name
        FORMS_NON_DICT[page_idx].label = new_label
        save_forms_to_file(FORMS_NON_DICT)
        flash("Page renamed successfully", "success")
    else:
        flash("Both name and label are required.", "error")

    return redirect(url_for("form_editor.list_forms"))
