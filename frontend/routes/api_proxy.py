import json
import logging

from flask import Blueprint, render_template, request

logger = logging.getLogger(__name__)

from services.case_service import CaseService
from services.chat_service import ChatService
from services.pdf_service import PdfService
from services.voice_service import VoiceService
from utils.api_client import APIError
from utils.auth import get_token, login_required

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/cases/create", methods=["POST"])
@login_required
def create_case():
    token = get_token()
    description = (
        request.form.get("description", "").strip()
        or request.form.get("message", "").strip()
    )
    language = request.form.get("language", "en")

    if not description:
        return render_template(
            "partials/error_fragment.html",
            message="Please describe your legal issue.",
        ), 400

    try:
        case = CaseService(token).create_case(description, language)
        detail = CaseService(token).get_case(case["case_id"])
        case = {**case, **{k: detail[k] for k in ("legal_notice_draft", "description", "pdf_url") if k in detail}}
        return render_template(
            "partials/case_response.html",
            case=case,
            user_message=description,
        )
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/cases/<case_id>/chat", methods=["POST"])
@login_required
def chat(case_id: str):
    token = get_token()
    message = request.form.get("message", "").strip()
    notice_draft = request.form.get("current_notice_draft", "")

    if not message:
        return "", 400

    try:
        response = ChatService(token).send_message(
            case_id=case_id,
            message=message,
            current_notice_draft=notice_draft,
        )
        return render_template(
            "partials/chat_response.html",
            response=response,
            user_message=message,
            case_id=case_id,
        )
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/cases/<case_id>/pdf", methods=["POST"])
@login_required
def generate_pdf(case_id: str):
    token = get_token()
    try:
        result = PdfService(token).generate(case_id)
        return render_template("partials/pdf_success.html", pdf=result, case_id=case_id)
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/cases/<case_id>/delete", methods=["POST"])
@login_required
def delete_case(case_id: str):
    token = get_token()
    try:
        CaseService(token).delete_case(case_id)
        return render_template("partials/case_deleted.html")
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/voice/transcribe", methods=["POST"])
@login_required
def transcribe():
    audio_file = request.files.get("audio_file")
    if not audio_file:
        return render_template(
            "partials/error_fragment.html",
            message="No audio file provided.",
        ), 400

    language = request.form.get("language", "en")
    try:
        result = VoiceService().transcribe(
            audio_file.read(),
            audio_file.filename or "recording.webm",
            language,
        )
        return render_template(
            "partials/transcript_result.html",
            transcript=result.get("transcript", ""),
        )
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/cases/<case_id>/execute-step/<int:step_number>", methods=["POST"])
@login_required
def execute_step(case_id: str, step_number: int):
    token = get_token()
    collected_info_str = request.form.get("collected_info", "{}")
    try:
        collected_info = json.loads(collected_info_str)
    except (json.JSONDecodeError, TypeError):
        collected_info = {}
    for key, val in request.form.items():
        if key.startswith("field_") and val.strip():
            collected_info[key[6:]] = val.strip()
    try:
        response = ChatService(token).execute_action(
            case_id=case_id,
            step_number=step_number,
            collected_info=collected_info,
        )
        logger.info("execute_step response: %s", response)
        if response.get("done") and response.get("document"):
            doc = response["document"]
            docs = CaseService(token).get_documents(case_id)
            return render_template(
                "partials/step_document_success.html",
                response=response,
                doc=doc,
                documents=docs,
                case_id=case_id,
            )
        if response.get("clarifying_questions"):
            return render_template(
                "partials/clarify_info.html",
                response=response,
                case_id=case_id,
                step_number=step_number,
                collected_info_json=json.dumps(collected_info),
            )
        return render_template(
            "partials/chat_response.html",
            response=response,
            user_message="",
            case_id=case_id,
        )
    except APIError as e:
        logger.error("execute_step API error: %s", e.message)
        return render_template("partials/error_fragment.html", message=e.message), e.status_code
    except Exception as e:
        logger.error("execute_step error: %s", e, exc_info=True)
        return render_template("partials/error_fragment.html", message=str(e)), 500


@api_bp.route("/cases/<case_id>/documents/<doc_id>", methods=["PUT"])
@login_required
def update_document(case_id: str, doc_id: str):
    token = get_token()
    data = request.get_json() or {}
    content = data.get("content", "")
    status = data.get("status", "draft")
    try:
        CaseService(token).update_document(case_id, doc_id, content, status)
        documents = CaseService(token).get_documents(case_id)
        return render_template(
            "partials/notice_panel.html",
            draft=content,
            case_id=case_id,
            documents=documents,
            active_doc_id=doc_id,
            pdf_url=None,
        )
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/cases/<case_id>/select-doc/<doc_id>")
@login_required
def select_document(case_id: str, doc_id: str):
    token = get_token()
    try:
        documents = CaseService(token).get_documents(case_id)
        doc = next((d for d in documents if d.get("id") == doc_id), None)
        return render_template(
            "partials/notice_panel.html",
            draft=doc.get("content", "") if doc else "",
            case_id=case_id,
            documents=documents,
            active_doc_id=doc_id,
            pdf_url=None,
        )
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/cases/<case_id>/documents/<doc_id>/preview", methods=["POST"])
@login_required
def preview_document(case_id: str, doc_id: str):
    token = get_token()
    try:
        pdf_bytes = CaseService(token).preview_document(case_id, doc_id)
        import base64
        b64 = base64.b64encode(pdf_bytes).decode()
        return render_template(
            "partials/pdf_preview.html",
            pdf_base64=b64,
            doc_id=doc_id,
            case_id=case_id,
        )
    except APIError as e:
        return render_template("partials/error_fragment.html", message=e.message), e.status_code


@api_bp.route("/sidebar")
@login_required
def sidebar():
    token = get_token()
    from services.auth_service import AuthService
    from utils.formatters import group_cases_by_date

    try:
        profile = AuthService(token).get_profile()
        cases_data = CaseService(token).list_cases()
        case_groups = group_cases_by_date(cases_data.get("cases", []))
    except APIError:
        profile = {}
        case_groups = {}

    active_case = request.args.get("active_case")
    return render_template(
        "partials/sidebar.html",
        profile=profile,
        case_groups=case_groups,
        active_case=active_case,
    )
