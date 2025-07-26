from flask import Blueprint, render_template, request, redirect, url_for
from form_config import FORMS_NON_DICT, save_forms_to_file, reset_forms
from models import FormField, FormPage

form_editor_bp = Blueprint("form_editor", __name__, url_prefix="/admin/forms")

@form_editor_bp.route("/")
def list_forms():
    return render_template("admin/form_editor.html", forms=FORMS_NON_DICT)

@form_editor_bp.route("/edit/<int:page_idx>/<int:field_idx>", methods=["GET", "POST"])
def edit_field(page_idx, field_idx):
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
    if page_idx == 0:
        return "Cannot add fields to Page 0.", 403

    new_field = FormField.text(name="new_field", label="New Field")
    FORMS_NON_DICT[page_idx].fields.append(new_field)
    save_forms_to_file(FORMS_NON_DICT)
    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/delete_field/<int:page_idx>/<int:field_idx>", methods=["POST"])
def delete_field(page_idx, field_idx):
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
    if page_idx == 0:
        return "Cannot delete Page 0.", 403

    if 0 <= page_idx < len(FORMS_NON_DICT):
        del FORMS_NON_DICT[page_idx]
        save_forms_to_file(FORMS_NON_DICT)

    return redirect(url_for("form_editor.list_forms"))

@form_editor_bp.route("/move_page/<int:page_idx>/<string:direction>", methods=["POST"])
def move_page(page_idx, direction):
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
    reset_forms()
    return render_template("admin/form_editor.html", forms=FORMS_NON_DICT)
