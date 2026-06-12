from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.auth_service import AuthService
from utils.api_client import APIError
from utils.auth import login_required, login_user, logout_user

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        try:
            result = AuthService().login(email, password)
            login_user(result["access_token"], result["email"], result["full_name"])
            return redirect(url_for("dashboard.index"))
        except APIError as e:
            flash(e.message, "error")
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        language = request.form.get("preferred_language", "en")
        try:
            result = AuthService().register(email, password, full_name, language)
            login_user(result["access_token"], result["email"], result["full_name"])
            return redirect(url_for("dashboard.index"))
        except APIError as e:
            flash(e.message, "error")
    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
