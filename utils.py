from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user

from models import Role


def approved_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_approved:
            return redirect(url_for("auth.pending_approval"))
        return fn(*args, **kwargs)

    return wrapper


def roles_required(*roles: Role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not current_user.is_approved:
                return redirect(url_for("auth.pending_approval"))
            if current_user.role not in roles:
                flash("You do not have permission to access that area.", "error")
                return redirect(url_for("main.dashboard"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def parse_dt(value: str):
    from datetime import datetime

    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
