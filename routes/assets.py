from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import Asset, Document, Role, uuid_str
from routes import assets_bp
from utils import approved_required, roles_required


@assets_bp.route("/")
@login_required
@approved_required
def index():
    assets = Asset.query.order_by(Asset.area, Asset.asset_code).all()
    documents = Document.query.order_by(Document.uploaded_at.desc()).all()
    return render_template("assets/index.html", assets=assets, documents=documents)


@assets_bp.route("/new", methods=["POST"])
@login_required
@approved_required
@roles_required(Role.ADMIN, Role.ENGINEER)
def create():
    code = (request.form.get("asset_code") or "").strip().upper()
    name = (request.form.get("asset_name") or "").strip()
    category = (request.form.get("category") or "").strip()
    area = (request.form.get("area") or "").strip()
    if not all([code, name, category, area]):
        flash("All asset fields are required.", "error")
        return redirect(url_for("assets.index"))
    if Asset.query.filter_by(asset_code=code).first():
        flash("Asset code already exists.", "error")
        return redirect(url_for("assets.index"))
    db.session.add(Asset(id=uuid_str(), asset_code=code, asset_name=name, category=category, area=area))
    db.session.commit()
    flash("Asset added to the plant directory.", "success")
    return redirect(url_for("assets.index"))
