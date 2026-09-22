import csv
import io
from datetime import datetime

from flask import Response, jsonify, request
from flask_login import current_user, login_required

from extensions import db
from models import Asset, BreakdownRecord, BreakdownStatus
from routes import api_bp
from routes.main import analytics_payload
from services.rag import rag_engine
from utils import approved_required, parse_dt


def _next_code():
    last = BreakdownRecord.query.order_by(BreakdownRecord.created_at.desc()).first()
    if last and last.code and last.code.startswith("R"):
        digits = "".join(ch for ch in last.code[1:] if ch.isdigit())
        if digits:
            return f"R{int(digits) + 1:011d}"
    return "R00000053999"


@api_bp.route("/analytics")
@login_required
@approved_required
def analytics():
    return jsonify(analytics_payload())


@api_bp.route("/records")
@login_required
@approved_required
def records():
    q = (request.args.get("q") or "").strip().lower()
    category = request.args.get("category") or "ALL"
    status = request.args.get("status") or "ALL"
    asset_code = request.args.get("asset") or "ALL"
    staff = request.args.get("staff") or "ALL"
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    sort_by = request.args.get("sort_by") or "received_on"
    sort_dir = (request.args.get("sort_dir") or "desc").lower()

    query = BreakdownRecord.query

    if category != "ALL":
        query = query.filter(BreakdownRecord.category == category)
    if status != "ALL":
        query = query.filter(BreakdownRecord.status.ilike(status))
    if asset_code != "ALL":
        query = query.filter(BreakdownRecord.asset_code == asset_code)
    if staff != "ALL":
        query = query.filter(BreakdownRecord.staff_member == staff)

    records_list = query.all()
    payload = []

    for rec in records_list:
        rec_dt = rec.received_on.strftime("%Y-%m-%d") if rec.received_on else ""
        if date_from and rec_dt and rec_dt < date_from:
            continue
        if date_to and rec_dt and rec_dt > date_to:
            continue

        if q:
            search_blob = " ".join(
                [
                    rec.code or "",
                    rec.asset_code or "",
                    rec.asset_description or "",
                    rec.description or "",
                    rec.staff_member or "",
                    rec.work_performed or "",
                    rec.notes or "",
                    rec.category or "",
                    rec.status or "",
                ]
            ).lower()
            if q not in search_blob:
                continue

        payload.append(rec.to_dict())

    # Sorting
    key_mapping = {
        "code": lambda x: x.get("code", ""),
        "received_on": lambda x: x.get("receivedOn", ""),
        "receivedOn": lambda x: x.get("receivedOn", ""),
        "completed_on": lambda x: x.get("completedOn", ""),
        "completedOn": lambda x: x.get("completedOn", ""),
        "asset_code": lambda x: x.get("assetCode", ""),
        "assetCode": lambda x: x.get("assetCode", ""),
        "asset_description": lambda x: x.get("assetDescription", ""),
        "assetDescription": lambda x: x.get("assetDescription", ""),
        "description": lambda x: x.get("description", ""),
        "staff_member": lambda x: x.get("staffMember", ""),
        "staffMember": lambda x: x.get("staffMember", ""),
        "status": lambda x: x.get("status", ""),
        "category": lambda x: x.get("category", ""),
        "work_performed": lambda x: x.get("workPerformed", ""),
        "workPerformed": lambda x: x.get("workPerformed", ""),
        "notes": lambda x: x.get("notes", ""),
    }
    sort_fn = key_mapping.get(sort_by, lambda x: x.get("receivedOn", ""))
    reverse = sort_dir == "desc"
    payload.sort(key=sort_fn, reverse=reverse)

    return jsonify(payload)


@api_bp.route("/records/<record_id>/inline-edit", methods=["POST"])
@login_required
@approved_required
def inline_edit(record_id):
    if not current_user.can_write():
        return jsonify({"ok": False, "error": "Insufficient permissions"}), 403

    record = BreakdownRecord.query.get_or_404(record_id)
    data = request.get_json(silent=True) or request.form or {}

    if "workPerformed" in data:
        record.work_performed = data["workPerformed"]
    elif "work_performed" in data:
        record.work_performed = data["work_performed"]

    if "notes" in data:
        record.notes = data["notes"]

    if "status" in data:
        new_status = str(data["status"]).strip()
        if new_status:
            record.status = new_status
            if new_status.lower() == "completed" and not record.completed_on:
                record.completed_on = datetime.utcnow()

    if "assetDescription" in data:
        record.asset_description = data["assetDescription"]
    elif "asset_description" in data:
        record.asset_description = data["asset_description"]

    if "description" in data:
        record.description = data["description"]

    if "category" in data:
        record.category = data["category"]

    rag_engine.index_record(record)
    db.session.commit()
    return jsonify({"ok": True, "record": record.to_dict()})


@api_bp.route("/records/<record_id>/status", methods=["POST"])
@login_required
@approved_required
def set_status(record_id):
    record = BreakdownRecord.query.get_or_404(record_id)
    data = request.get_json(silent=True) or request.form or {}
    status = data.get("status")
    if not status:
        return jsonify({"ok": False, "error": "Status is required"}), 400

    record.status = str(status).strip()
    if record.status.lower() == "completed" and not record.completed_on:
        record.completed_on = datetime.utcnow()

    rag_engine.index_record(record)
    db.session.commit()
    return jsonify({"ok": True, "record": record.to_dict()})


@api_bp.route("/records/export")
@login_required
@approved_required
def export_records():
    records_list = BreakdownRecord.query.order_by(BreakdownRecord.received_on.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Code",
            "Received On",
            "Completed On",
            "Asset Code",
            "Asset Description",
            "Description",
            "Staff Member",
            "Status",
            "Work Performed",
            "Notes",
            "Category",
        ]
    )
    for r in records_list:
        writer.writerow(
            [
                r.code,
                r.received_on.strftime("%Y-%m-%d %H:%M") if r.received_on else "",
                r.completed_on.strftime("%Y-%m-%d %H:%M") if r.completed_on else "",
                r.asset_code,
                r.asset_description,
                r.description,
                r.staff_member,
                r.status,
                r.work_performed or "",
                r.notes or "",
                r.category or "",
            ]
        )
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ForgeMind_Breakdown_Logs.csv"},
    )


@api_bp.route("/records/import", methods=["POST"])
@login_required
@approved_required
def import_records():
    if not current_user.can_write():
        return jsonify({"ok": False, "error": "Insufficient permissions to import records"}), 403

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    try:
        content = file.stream.read().decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        imported = 0

        for row in reader:
            normalized = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if k}
            code = normalized.get("code") or normalized.get("record_code") or _next_code()
            if BreakdownRecord.query.filter_by(code=code).first():
                code = _next_code()

            asset_code = normalized.get("asset_code") or normalized.get("asset") or "UNASSIGNED"
            asset_desc = (
                normalized.get("asset_description")
                or normalized.get("asset_name")
                or "Industrial Equipment"
            )
            description = (
                normalized.get("description")
                or normalized.get("problem")
                or normalized.get("problem_description")
                or "Breakdown incident reported"
            )
            staff = (
                normalized.get("staff_member")
                or normalized.get("technician")
                or normalized.get("staff")
                or current_user.name
            )
            status = normalized.get("status") or "Approved"
            work = normalized.get("work_performed") or normalized.get("corrective_action") or ""
            notes = normalized.get("notes") or ""
            category = normalized.get("category") or "Mechanical"

            received = parse_dt(normalized.get("received_on") or normalized.get("receivedon")) or datetime.utcnow()
            completed = parse_dt(normalized.get("completed_on") or normalized.get("completedon"))

            rec = BreakdownRecord(
                code=code,
                asset_code=asset_code,
                asset_description=asset_desc,
                description=description,
                staff_member=staff,
                status=status,
                received_on=received,
                completed_on=completed,
                work_performed=work,
                notes=notes,
                category=category,
            )
            db.session.add(rec)
            db.session.flush()
            rag_engine.index_record(rec)
            imported += 1

        db.session.commit()
        return jsonify({"ok": True, "count": imported, "message": f"Successfully imported {imported} breakdown records."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Failed to parse import file: {str(e)}"}), 400


@api_bp.route("/assets")
@login_required
@approved_required
def assets_search():
    q = (request.args.get("q") or "").strip().lower()
    assets = Asset.query.order_by(Asset.asset_code).all()
    if q:
        assets = [
            a
            for a in assets
            if q in a.asset_code.lower() or q in a.asset_name.lower() or q in a.area.lower()
        ]
    return jsonify(
        [
            {
                "id": a.id,
                "asset_code": a.asset_code,
                "asset_name": a.asset_name,
                "category": a.category,
                "area": a.area,
            }
            for a in assets
        ]
    )


@api_bp.route("/chat", methods=["POST"])
@login_required
@approved_required
def chat():
    data = request.get_json(silent=True) or request.form or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400
    result = rag_engine.answer(query, k=5)
    return jsonify(result)

