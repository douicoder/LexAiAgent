from functools import wraps

from flask import redirect, session, url_for


def login_user(token: str, email: str, full_name: str) -> None:
    session.permanent = True
    session["access_token"] = token
    session["email"] = email
    session["full_name"] = full_name


def logout_user() -> None:
    session.clear()


def get_token() -> str | None:
    return session.get("access_token")


def is_authenticated() -> bool:
    return bool(session.get("access_token"))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated
