import os
import uuid
from datetime import datetime

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import Asset, BreakdownRecord, BreakdownStatus
from routes import knowledge_bp
from services.rag import rag_engine
from utils import approved_required, parse_dt

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def next_record_code() -> str:
    last = BreakdownRecord.query.order_by(BreakdownRecord.created_at.desc()).first()
    if last and last.code and last.code.startswith("R"):
        digits = "".join(ch for ch in last.code[1:] if ch.isdigit())
        if digits:
            return f"R{int(digits) + 1:011d}"
    return "R00000053898"


def save_photos(files) -> list[str]:
    urls = []
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            continue
        name = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(upload_dir, secure_filename(name))
        f.save(path)
        urls.append(url_for("static", filename=f"uploads/{name}"))
    return urls


@knowledge_bp.route("/")
@login_required
@approved_required
def index():
    assets = Asset.query.order_by(Asset.asset_code).all()
    technicians = sorted({r.staff_member for r in BreakdownRecord.query.all() if r.staff_member})
    return render_template("knowledge/index.html", assets=assets, technicians=technicians)


@knowledge_bp.route("/new", methods=["GET", "POST"])
@login_required
@approved_required
def create():
    if not current_user.can_write():
        flash("Viewers have read-only access and cannot log breakdowns.", "error")
        return redirect(url_for("knowledge.index"))
    assets = Asset.query.order_by(Asset.asset_code).all()
    if request.method == "POST":
        record = _save_from_form()
        if record:
            flash("Breakdown captured and queued for vector indexing.", "success")
            if request.form.get("modal"):
                return jsonify({"ok": True, "record": record.to_dict()})
            return redirect(url_for("knowledge.index"))
        if request.form.get("modal"):
            return jsonify({"ok": False, "error": "Missing required fields"}), 400
    return render_template("knowledge/new.html", assets=assets, suggested_code=next_record_code())


@knowledge_bp.route("/<record_id>")
@login_required
@approved_required
def detail(record_id):
    record = BreakdownRecord.query.get_or_404(record_id)
    if request.args.get("json"):
        return jsonify(record.to_dict())
    return render_template("knowledge/detail.html", record=record)


def _save_from_form():
    asset_id = request.form.get("asset_id")
    asset_code = request.form.get("asset_code") or ""
    asset_desc = request.form.get("asset_description") or ""

    if asset_id and not (asset_code and asset_desc):
        asset = Asset.query.get(asset_id)
        if asset:
            asset_code = asset_code or asset.asset_code
            asset_desc = asset_desc or asset.asset_name

    problem = (request.form.get("problem_description") or request.form.get("description") or "").strip()
    work = (request.form.get("work_performed") or "").strip()
    category = request.form.get("category") or "Mechanical"

    if not asset_code:
        asset_code = request.form.get("asset_search") or "UNASSIGNED"
    if not asset_desc:
        asset_desc = "Plant Machinery"

    if not problem or not work:
        flash("Problem description and work performed are required.", "error")
        return None

    code = (request.form.get("code") or "").strip() or next_record_code()
    if BreakdownRecord.query.filter_by(code=code).first():
        code = next_record_code()

    record = BreakdownRecord(
        code=code,
        asset_code=asset_code,
        asset_description=asset_desc,
        description=problem,
        staff_member=current_user.name,
        received_on=parse_dt(request.form.get("received_on")) or datetime.utcnow(),
        completed_on=parse_dt(request.form.get("completed_on")),
        category=category,
        work_performed=work,
        notes=request.form.get("notes") or "",
        root_cause=request.form.get("root_cause") or "",
        corrective_action=request.form.get("corrective_action") or "",
        lesson_learned=request.form.get("lesson_learned") or "",
        downtime_hours=float(request.form.get("downtime_hours") or 0),
        photo_urls=save_photos(request.files.getlist("photos")),
        status="Pending",
    )
    db.session.add(record)
    db.session.flush()
    rag_engine.index_record(record)
    db.session.commit()
    return record

