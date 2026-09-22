import os

from flask import Flask, render_template
from flask_login import current_user

from config import Config
from extensions import db, login_manager, migrate, oauth
from models import AccountStatus, BreakdownStatus, Role
from services.rag import rag_engine


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    oauth.init_app(app)
    rag_engine.init_app(app)

    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.assets import assets_bp
    from routes.auth import auth_bp
    from routes.knowledge import knowledge_bp
    from routes.main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_globals():
        return {
            "current_user": current_user,
            "Role": Role,
            "AccountStatus": AccountStatus,
            "BreakdownStatus": BreakdownStatus,
        }

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Page not found"), 404

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
