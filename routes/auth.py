from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db, login_manager, oauth
from models import AccountStatus, Role, User
from routes import auth_bp


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


def _already_registered(name: str) -> bool:
    return name in getattr(oauth, "_clients", {})


def _register_oauth():
    cfg = current_app.config
    if cfg.get("GOOGLE_CLIENT_ID") and not _already_registered("google"):
        oauth.register(
            name="google",
            client_id=cfg["GOOGLE_CLIENT_ID"],
            client_secret=cfg["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    if cfg.get("MICROSOFT_CLIENT_ID") and not _already_registered("microsoft"):
        oauth.register(
            name="microsoft",
            client_id=cfg["MICROSOFT_CLIENT_ID"],
            client_secret=cfg["MICROSOFT_CLIENT_SECRET"],
            server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    if cfg.get("APPLE_CLIENT_ID") and not _already_registered("apple"):
        oauth.register(
            name="apple",
            client_id=cfg["APPLE_CLIENT_ID"],
            client_secret=cfg["APPLE_CLIENT_SECRET"],
            authorize_url="https://appleid.apple.com/auth/authorize",
            access_token_url="https://appleid.apple.com/auth/token",
            client_kwargs={"scope": "name email", "response_mode": "form_post"},
        )


@auth_bp.before_app_request
def ensure_oauth():
    _register_oauth()


@auth_bp.route("/login", methods=["GET", "POST"])
@auth_bp.route("/auth/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html")
        login_user(user)
        if not user.is_approved:
            return redirect(url_for("auth.pending_approval"))
        return redirect(url_for("main.dashboard"))
    return render_template("auth/login.html")


@auth_bp.route("/demo-login/<role>")
@auth_bp.route("/auth/demo-login/<role>")
def demo_login(role):
    role_email_map = {
        "admin": "admin@forgemind.local",
        "engineer": "engineer@forgemind.local",
        "artisan": "safuan@forgemind.local",
        "viewer": "viewer@forgemind.local",
        "pending": "pending@forgemind.local",
    }
    email = role_email_map.get(role.lower())
    if not email:
        # Fallback to test user or first matching role
        user = User.query.filter(User.role.ilike(role)).first()
    else:
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User.query.filter(User.role.ilike(role)).first()

    if not user:
        flash("Demo user not found. Please run seed script first.", "error")
        return redirect(url_for("auth.login"))

    login_user(user)
    if not user.is_approved:
        return redirect(url_for("auth.pending_approval"))
    flash(f"Signed in as demo {user.role} ({user.name}).", "success")
    return redirect(url_for("main.dashboard"))


@auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/auth/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not name or not email or not password:
            flash("Name, email, and password are required.", "error")
            return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("auth/register.html")
        user = User(
            name=name,
            email=email,
            role="ARTISAN",
            status="PENDING",
            auth_provider="manual",
        )
        user.set_password(password)
        if User.query.count() == 0:
            user.role = "ADMIN"
            user.status = "APPROVED"
        db.session.add(user)
        db.session.commit()
        login_user(user)
        if user.is_approved:
            flash("Welcome to ForgeMind.", "success")
            return redirect(url_for("main.dashboard"))
        return redirect(url_for("auth.pending_approval"))
    return render_template("auth/register.html")


@auth_bp.route("/logout")
@auth_bp.route("/auth/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out successfully.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/pending-approval")
@login_required
def pending_approval():
    if current_user.is_approved:
        return redirect(url_for("main.dashboard"))
    return render_template("auth/pending.html")


@auth_bp.route("/oauth/<provider>")
def oauth_start(provider):
    provider = provider.lower()
    _register_oauth()
    client = oauth.create_client(provider)
    if client is None:
        # Graceful demo mock authentication when client secrets are not configured in local environment
        mock_user_email = f"{provider}.artisan@forgemind.local"
        user = User.query.filter_by(email=mock_user_email).first()
        if not user:
            user = User(
                name=f"{provider.title()} Verified Tech",
                email=mock_user_email,
                role="ARTISAN",
                status="APPROVED",
                auth_provider=provider,
            )
            db.session.add(user)
            db.session.commit()
        login_user(user)
        flash(f"Signed in via {provider.title()} OAuth.", "success")
        return redirect(url_for("main.dashboard"))

    redirect_uri = url_for("auth.oauth_callback", provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@auth_bp.route("/oauth/<provider>/callback", methods=["GET", "POST"])
def oauth_callback(provider):
    provider = provider.lower()
    _register_oauth()
    client = oauth.create_client(provider)
    if client is None:
        flash("OAuth provider is not configured.", "error")
        return redirect(url_for("auth.login"))
    token = client.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    if not userinfo and hasattr(client, "userinfo"):
        try:
            userinfo = client.userinfo()
        except Exception:
            userinfo = {}
    email = (userinfo.get("email") or "").lower()
    name = userinfo.get("name") or userinfo.get("given_name") or email.split("@")[0]
    if not email:
        flash("The identity provider did not return an email address.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            name=name,
            email=email,
            role="ARTISAN",
            status="PENDING",
            auth_provider=provider,
        )
        if User.query.count() == 0:
            user.role = "ADMIN"
            user.status = "APPROVED"
        db.session.add(user)
        db.session.commit()
    login_user(user)
    if not user.is_approved:
        return redirect(url_for("auth.pending_approval"))
    return redirect(url_for("main.dashboard"))
