from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import AccountStatus, BreakdownRecord, BreakdownStatus, Role, User
from routes import admin_bp
from services.rag import rag_engine
from utils import approved_required, roles_required


@admin_bp.route("/")
@login_required
@approved_required
@roles_required(Role.ADMIN, "ADMIN")
def users():
    people = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", people=people, statuses=AccountStatus, roles=Role)


@admin_bp.route("/users/<user_id>/status", methods=["POST"])
@login_required
@approved_required
@roles_required(Role.ADMIN, "ADMIN")
def set_user_status(user_id):
    user = User.query.get_or_404(user_id)
    status = (request.form.get("status") or (request.json or {}).get("status") or "").strip().upper()
    if status not in {"PENDING", "APPROVED", "REJECTED"}:
        flash("Invalid account status.", "error")
        return redirect(url_for("admin.users"))

    user.status = status
    db.session.commit()
    if request.is_json or request.headers.get("HX-Request"):
        return jsonify({"ok": True, "status": user.status})
    flash(f"{user.name} marked as {user.status}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<user_id>/role", methods=["POST"])
@login_required
@approved_required
@roles_required(Role.ADMIN, "ADMIN")
def set_user_role(user_id):
    user = User.query.get_or_404(user_id)
    role = (request.form.get("role") or "").strip().upper()
    if role not in {"ADMIN", "ENGINEER", "ARTISAN", "VIEWER"}:
        flash("Invalid role specified.", "error")
        return redirect(url_for("admin.users"))

    user.role = role
    db.session.commit()
    flash(f"{user.name} role updated to {user.role}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/records/<record_id>/status", methods=["POST"])
@login_required
@approved_required
@roles_required(Role.ADMIN, Role.ENGINEER, "ADMIN", "ENGINEER")
def set_record_status(record_id):
    record = BreakdownRecord.query.get_or_404(record_id)
    status = (request.form.get("status") or (request.json or {}).get("status") or "").strip()
    if not status:
        return jsonify({"ok": False, "error": "Invalid status"}), 400

    record.status = status
    if record.status.lower() == "completed" and not record.completed_on:
        record.completed_on = datetime.utcnow()

    rag_engine.index_record(record)
    db.session.commit()
    return jsonify({"ok": True, "record": record.to_dict()})

