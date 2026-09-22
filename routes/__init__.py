from flask import Blueprint

auth_bp = Blueprint("auth", __name__)
main_bp = Blueprint("main", __name__)
knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
assets_bp = Blueprint("assets", __name__, url_prefix="/assets")
api_bp = Blueprint("api", __name__, url_prefix="/api")
