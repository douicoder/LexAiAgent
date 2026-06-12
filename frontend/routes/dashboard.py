from flask import Blueprint, render_template

from services.auth_service import AuthService
from services.case_service import CaseService
from utils.api_client import APIError
from utils.auth import get_token, login_required
from utils.constants import SUGGESTIONS
from utils.formatters import group_cases_by_date

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    token = get_token()
    profile = {}
    case_groups = {}
    try:
        profile = AuthService(token).get_profile()
        cases_data = CaseService(token).list_cases()
        case_groups = group_cases_by_date(cases_data.get("cases", []))
    except APIError:
        pass
    return render_template(
        "dashboard/dashboard.html",
        profile=profile,
        case_groups=case_groups,
        suggestions=SUGGESTIONS,
        active_case=None,
    )
