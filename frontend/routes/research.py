from flask import Blueprint, render_template, request

from services.auth_service import AuthService
from services.case_service import CaseService
from services.document_service import DocumentService
from utils.api_client import APIError
from utils.auth import get_token, login_required
from utils.formatters import group_cases_by_date

research_bp = Blueprint("research", __name__)


@research_bp.route("/research")
@login_required
def index():
    token = get_token()
    profile = {}
    case_groups = {}
    results = []
    query = request.args.get("q", "").strip()
    top_k = int(request.args.get("top_k", 10))
    acts = request.args.get("acts", "").strip() or None
    min_score = float(request.args.get("min_score", 0.0))
    hybrid = request.args.get("hybrid", "true").lower() == "true"
    rerank = request.args.get("rerank", "false").lower() == "true"

    try:
        profile = AuthService(token).get_profile()
        cases_data = CaseService(token).list_cases()
        case_groups = group_cases_by_date(cases_data.get("cases", []))
        if len(query) >= 2:
            search_data = DocumentService().search(
                query=query,
                top_k=top_k,
                acts=acts,
                min_score=min_score,
                hybrid=hybrid,
                rerank=rerank,
            )
            results = search_data.get("results", [])
    except APIError:
        pass

    return render_template(
        "research/research.html",
        profile=profile,
        case_groups=case_groups,
        results=results,
        query=query,
        top_k=top_k,
        acts=acts or "",
        min_score=min_score,
        hybrid=hybrid,
        rerank=rerank,
        active_case=None,
    )
