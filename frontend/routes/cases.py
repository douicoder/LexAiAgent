from flask import Blueprint, redirect, render_template, url_for

from services.auth_service import AuthService
from services.case_service import CaseService
from utils.api_client import APIError
from utils.auth import get_token, login_required
from utils.formatters import group_cases_by_date

cases_bp = Blueprint("cases", __name__)


@cases_bp.route("/case/<case_id>")
@login_required
def view(case_id: str):
    token = get_token()
    try:
        profile = AuthService(token).get_profile()
        case_service = CaseService(token)
        case = case_service.get_case(case_id)
        messages = case_service.get_messages(case_id)
        cases_data = case_service.list_cases()
        case_groups = group_cases_by_date(cases_data.get("cases", []))
    except APIError:
        return redirect(url_for("dashboard.index"))

    documents = case_service.get_documents(case_id) if case.get("status") != "processing" else []
    active_doc_id = documents[0].get("id") if documents else None

    return render_template(
        "cases/case.html",
        profile=profile,
        case=case,
        case_id=case_id,
        messages=messages,
        case_groups=case_groups,
        active_case=case_id,
        case_documents=documents,
        active_doc_id=active_doc_id,
    )
