from datetime import datetime, timedelta

from flask import render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import BreakdownRecord
from routes import main_bp
from utils import approved_required


@main_bp.route("/")
@login_required
@approved_required
def dashboard():
    total = BreakdownRecord.query.count()
    avg_dt = db.session.query(func.coalesce(func.avg(BreakdownRecord.downtime_hours), 0)).scalar() or 0
    pending = BreakdownRecord.query.filter(BreakdownRecord.status.ilike("Pending")).count()
    completed = BreakdownRecord.query.filter(BreakdownRecord.status.ilike("Completed")).count()
    unresolved = total - completed
    return render_template(
        "dashboard.html",
        total=total,
        avg_dt=round(float(avg_dt), 1),
        pending=pending,
        unresolved=max(0, unresolved),
        user=current_user,
    )


@main_bp.route("/chat")
@login_required
@approved_required
def chat():
    return render_template("chat.html")


def analytics_payload():
    total = BreakdownRecord.query.count()
    avg_dt = db.session.query(func.coalesce(func.avg(BreakdownRecord.downtime_hours), 0)).scalar() or 0
    pending = BreakdownRecord.query.filter(BreakdownRecord.status.ilike("Pending")).count()
    completed = BreakdownRecord.query.filter(BreakdownRecord.status.ilike("Completed")).count()
    unresolved = max(0, total - completed)

    since = datetime.utcnow() - timedelta(days=90)
    records = BreakdownRecord.query.filter(BreakdownRecord.received_on >= since).all()
    buckets = {}
    for rec in records:
        key = rec.received_on.strftime("%Y-%m-%d") if rec.received_on else "Unscheduled"
        buckets.setdefault(key, {"count": 0, "downtime": 0.0})
        buckets[key]["count"] += 1
        buckets[key]["downtime"] += rec.downtime_hours or 0

    trend_labels = sorted(buckets.keys())
    trend_counts = [buckets[d]["count"] for d in trend_labels]
    trend_dt = [round(buckets[d]["downtime"], 1) for d in trend_labels]

    cat_rows = (
        db.session.query(BreakdownRecord.category, func.count(BreakdownRecord.id))
        .group_by(BreakdownRecord.category)
        .all()
    )

    asset_rows = (
        db.session.query(
            BreakdownRecord.asset_code,
            BreakdownRecord.asset_description,
            func.count(BreakdownRecord.id),
            func.sum(BreakdownRecord.downtime_hours),
        )
        .group_by(BreakdownRecord.asset_code, BreakdownRecord.asset_description)
        .order_by(func.count(BreakdownRecord.id).desc())
        .limit(8)
        .all()
    )

    top_assets = [
        {
            "code": row[0],
            "name": row[1] or "",
            "count": int(row[2]),
            "downtime": float(row[3] or 0),
        }
        for row in asset_rows
    ]

    vectorized = BreakdownRecord.query.filter(BreakdownRecord.embedding.isnot(None)).count()
    pct = round((vectorized / total) * 100, 1) if total else 0

    return {
        "kpis": {
            "total": total,
            "avgDowntime": round(float(avg_dt), 1),
            "pending": pending,
            "unresolved": unresolved,
            "vectorizedPct": pct,
        },
        "trend": {"labels": trend_labels, "counts": trend_counts, "downtime": trend_dt},
        "categories": {
            "labels": [c or "Other" for c, _ in cat_rows],
            "values": [int(n) for _, n in cat_rows],
        },
        "topAssets": top_assets,
    }

