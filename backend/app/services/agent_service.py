import json
import uuid

from openai import AsyncOpenAI

from app.config import settings
from app.dto.agent_dto import (
    ActionButton,
    ActionStep,
    AnalyzeRequestDTO,
    AnalyzeResponseDTO,
    ChatRequestDTO,
    ChatResponseDTO,
    ClarifyingQuestion,
    DocumentDTO,
    ExecuteActionRequest,
    ExecuteActionResponse,
)
from app.helpers.legal_helper import LegalHelper
from app.helpers.text_helper import TextHelper
from app.interfaces.i_agent_service import IAgentService
from app.interfaces.i_rag_service import IRagService

LLM_MODEL = settings.LLM_MODEL
FAST_MODEL = "gpt-4o"

# ── Document type definitions ───────────────────────────────────────────
DOCUMENT_TYPES = {
    "demand_letter": {
        "title": "Formal Demand Letter",
        "required_info": ["tenant_name", "tenant_address", "landlord_name", "landlord_address", "deposit_amount", "property_address", "move_out_date"],
        "info_labels": {"tenant_name": "Your full name", "tenant_address": "Your current address", "landlord_name": "Landlord's full name", "landlord_address": "Landlord's address", "deposit_amount": "Security deposit amount (₹)", "property_address": "Rented property address", "move_out_date": "Date you vacated the property"},
    },
    "legal_notice": {
        "title": "Legal Notice",
        "required_info": ["sender_name", "sender_address", "recipient_name", "recipient_address", "subject", "details"],
        "info_labels": {"sender_name": "Your full name", "sender_address": "Your address", "recipient_name": "Recipient's full name", "recipient_address": "Recipient's address", "subject": "Subject of the notice", "details": "Brief description of the issue"},
    },
    "court_filing": {
        "title": "Court Filing / Petition",
        "required_info": ["petitioner_name", "petitioner_address", "respondent_name", "respondent_address", "court_name", "case_details", "relief_sought"],
        "info_labels": {"petitioner_name": "Your full name (Petitioner)", "petitioner_address": "Your address", "respondent_name": "Respondent's full name", "respondent_address": "Respondent's address", "court_name": "Name of the court", "case_details": "Detailed facts of the case", "relief_sought": "What relief you are seeking from the court"},
    },
    "affidavit": {
        "title": "Affidavit",
        "required_info": ["deponent_name", "deponent_address", "contents"],
        "info_labels": {"deponent_name": "Your full name (Deponent)", "deponent_address": "Your address", "contents": "Contents of the affidavit"},
    },
    "complaint": {
        "title": "Formal Complaint",
        "required_info": ["complainant_name", "complainant_address", "respondent_name", "complaint_details"],
        "info_labels": {"complainant_name": "Your full name (Complainant)", "complainant_address": "Your address", "respondent_name": "Respondent's name", "complaint_details": "Details of the complaint"},
    },
    "agreement": {
        "title": "Legal Agreement",
        "required_info": ["party_a_name", "party_a_address", "party_b_name", "party_b_address", "terms"],
        "info_labels": {"party_a_name": "First Party name", "party_a_address": "First Party address", "party_b_name": "Second Party name", "party_b_address": "Second Party address", "terms": "Key terms of the agreement"},
    },
}


def _extract_json(text: str) -> dict:
    text = text.strip()
    for end in range(len(text) - 1, -1, -1):
        if text[end] != "}":
            continue
        depth = 0
        in_string = False
        escape = False
        start = -1
        for j in range(end, -1, -1):
            char = text[j]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "}":
                depth += 1
            elif char == "{":
                depth -= 1
                if depth == 0:
                    start = j
                    break
        if start >= 0 and depth == 0:
            return json.loads(text[start: end + 1])
    raise ValueError("No valid JSON object found in text")


def _generate_doc_id() -> str:
    return str(uuid.uuid4())


class AgentService(IAgentService):
    def __init__(self, rag: IRagService):
        self.client = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.github.ai/inference",
        )
        self.rag = rag
        self.legal = LegalHelper()
        self.text = TextHelper()

    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        description = request.description
        if request.language == "hi":
            description = await self.text.translate_to_english(description)

        reasoning_trace = []

        # ── Round 1: Classify case ────────────────────────────────────────────
        classify_prompt = (
            f"Problem: {description}\n\n"
            f"Classify this legal problem into a JSON object:\n"
            f'{{"case_type": "tenancy_dispute|property_ownership|property_registration|other", '
            f'"severity": "low|medium|high|urgent", '
            f'"reasoning": "brief reason"}}'
        )

        response = await self.client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
            ],
            max_tokens=1000,
        )
        classify_text = response.choices[0].message.content.strip() or ""
        classification = _extract_json(classify_text)
        reasoning_trace.append(f"[classify_case] -> {classification}")

        # ── Round 2: Search law ───────────────────────────────────────────────
        search_prompt = (
            f"Case: {classification.get('case_type')} ({classification.get('severity')}). "
            f"{classification.get('reasoning', '')}\n\n"
            f"What specific search query should be used to find relevant Indian law sections?\n\n"
            f"Output a JSON object:\n"
            f'{{"query": "specific legal search terms"}}'
        )

        response = await self.client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
                {"role": "assistant", "content": classify_text},
                {"role": "user", "content": search_prompt},
            ],
            max_tokens=1000,
        )
        search_text = response.choices[0].message.content.strip() or ""
        search_args = _extract_json(search_text)
        query = search_args.get("query", description)

        law_sections = await self.rag.search(query=query, top_k=5)
        reasoning_trace.append(f"[search_law: '{query}'] -> {len(law_sections)} results")

        # ── Round 3: Generate steps + summary ─────────────────────────────────
        steps_prompt = (
            f"Original problem: {description}\n\n"
            f"Case classification: {json.dumps(classification, indent=2)}\n\n"
            f"Relevant law sections found:\n{json.dumps(law_sections, indent=2, default=str)}\n\n"
            f"Generate a step-by-step action plan for this legal case.\n\n"
            f"Return ONLY valid JSON with these exact keys. No markdown backticks. No extra text.\n"
            f"ai_message should be warm, empathetic, conversational.\n"
            f"summary should be 2-3 sentence summary of the case and recommended approach.\n\n"
            f"steps should be an array of actionable steps. Each step has:\n"
            f'  - "number": sequential integer\n'
            f'  - "text": clear instruction for the user\n'
            f'  - "action_type": one of "generate_document" (creates a legal document), '
            f'"wait" (waiting period), "info_gathering" (collect information)\n'
            f'  - "action_config": object with "doc_type" (one of: demand_letter, legal_notice, '
            f'court_filing, affidavit, complaint, agreement) and "title" for document actions\n\n'
            f'Example for a security deposit dispute:\n'
            f'{{"steps": [\n'
            f'  {{"number": 1, "text": "Send a formal demand letter to your landlord requesting the refund of your security deposit", "action_type": "generate_document", "action_config": {{"doc_type": "demand_letter", "title": "Formal Demand Letter for Security Deposit Refund"}}}}, \n'
            f'  {{"number": 2, "text": "Wait 30 days for your landlord to respond to the demand letter", "action_type": "wait", "action_config": {{"duration": "30 days"}}}}, \n'
            f'  {{"number": 3, "text": "If no response, file a complaint with the Rent Controller / Tenancy Tribunal", "action_type": "generate_document", "action_config": {{"doc_type": "complaint", "title": "Complaint to Rent Controller"}}}}, \n'
            f'  {{"number": 4, "text": "If the dispute remains unresolved, file a civil suit for recovery", "action_type": "generate_document", "action_config": {{"doc_type": "court_filing", "title": "Civil Suit for Recovery of Security Deposit"}}}}\n'
            f']}}}}\n\n"'
            f"Put your JSON answer after a line that says exactly 'FINAL_JSON:' and nothing else."
        )

        response = await self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": steps_prompt},
            ],
            max_tokens=8000,
        )
        final_text = response.choices[0].message.content.strip() or ""

        marker = "FINAL_JSON:"
        idx = final_text.rfind(marker)
        if idx >= 0:
            final_data = _extract_json(final_text[idx + len(marker):])
        else:
            final_data = _extract_json(final_text)

        steps_data = final_data.get("steps", [])
        action_steps = []
        for s in steps_data:
            action_steps.append(ActionStep(
                number=s.get("number", 1),
                text=s.get("text", ""),
                action_type=s.get("action_type", "info_gathering"),
                action_config=s.get("action_config", {}),
                status="pending",
            ))

        clarifying_questions = [
            ClarifyingQuestion(question=q.get("question", ""), key=q.get("key", ""))
            for q in final_data.get("clarifying_questions", [])
        ]

        action_buttons_items = [
            ActionButton(label=ab.get("label", ""), message=ab.get("message", ""), style=ab.get("style", "default"))
            for ab in final_data.get("action_buttons", [])
        ]

        return AnalyzeResponseDTO(
            case_type=classification.get("case_type", "other"),
            severity=classification.get("severity", "medium"),
            relevant_sections=law_sections,
            legal_notice_draft="",
            summary=final_data.get("summary", ""),
            next_steps=action_steps,
            reasoning_trace="\n".join(reasoning_trace),
            clarifying_questions=clarifying_questions,
            action_buttons=action_buttons_items,
            ai_message=final_data.get("ai_message", f"I've analyzed your case. Here's a step-by-step plan to help you resolve this matter."),
        )

    async def execute_action(
        self,
        request: ExecuteActionRequest,
        supabase_service=None,
    ) -> ExecuteActionResponse:
        if not supabase_service:
            return ExecuteActionResponse(
                reply="Internal error: database service not available.",
                done=True,
            )

        case = supabase_service.get_case_by_id(request.case_id)
        if not case:
            return ExecuteActionResponse(
                reply="Case not found.",
                done=True,
            )

        steps = case.get("next_steps", []) or []
        step = None
        for s in steps:
            if s.get("number") == request.step_number:
                step = s
                break
        if not step:
            return ExecuteActionResponse(
                reply="Step not found.",
                done=True,
            )

        action_type = step.get("action_type", "")
        if action_type != "generate_document":
            return ExecuteActionResponse(
                reply=f"Step {request.step_number}: {step.get('text', '')}",
                done=False,
                action_buttons=[ActionButton(label="Mark as done", message=f"Mark step {request.step_number} as completed", style="primary")],
            )

        action_config = step.get("action_config", {}) or {}
        doc_type = action_config.get("doc_type", "")
        doc_config = DOCUMENT_TYPES.get(doc_type)
        if not doc_config:
            doc_config = {
                "title": action_config.get("title", "Legal Document"),
                "required_info": ["details"],
                "info_labels": {"details": "Details of the matter"},
            }

        missing = [f for f in doc_config["required_info"] if f not in request.collected_info]
        if missing:
            questions = [
                ClarifyingQuestion(question=doc_config["info_labels"].get(f, f.replace("_", " ").title()), key=f)
                for f in missing
            ]
            return ExecuteActionResponse(
                reply=f"I need some information to draft the {doc_config['title']}. Please provide the following:",
                clarifying_questions=questions,
                missing_fields=missing,
                done=False,
            )

        description = case.get("description", "")
        case_type = case.get("case_type", "")
        severity = case.get("severity", "")
        relevant_sections = case.get("relevant_sections", []) or []

        gen_prompt = (
            f"You are drafting a legal document for an Indian legal case.\n\n"
            f"Document type: {doc_type}\n"
            f"Title: {doc_config['title']}\n\n"
            f"Case description: {description}\n"
            f"Case type: {case_type} ({severity})\n\n"
            f"Relevant law sections:\n{json.dumps(relevant_sections, indent=2, default=str)}\n\n"
            f"Information provided:\n{json.dumps(request.collected_info, indent=2)}\n\n"
            f"Generate the complete legal document in proper legal format.\n"
            f"Use appropriate legal language, sections, and references.\n"
            f"Make it formal and ready for use.\n\n"
            f"Return ONLY valid JSON with these exact keys:\n"
            f'{{"content": "the full legal document text"}}\n\n'
            f"No markdown backticks. No extra text."
        )

        response = await self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": gen_prompt},
            ],
            max_tokens=16000,
        )
        gen_text = response.choices[0].message.content.strip() or ""
        try:
            gen_data = _extract_json(gen_text)
        except ValueError:
            gen_data = {"content": gen_text}

        doc_content = gen_data.get("content", gen_text)

        doc_id = _generate_doc_id()
        now = __import__("datetime").datetime.utcnow().isoformat()

        try:
            supabase_service.create_document({
                "id": doc_id,
                "case_id": request.case_id,
                "doc_type": doc_type,
                "title": doc_config["title"],
                "content": doc_content,
                "status": "draft",
            })
        except Exception as e:
            return ExecuteActionResponse(
                reply=f"I generated the document but could not save it. The database table `case_documents` may not exist. Error: {e}",
                document=DocumentDTO(
                    id=doc_id,
                    case_id=request.case_id,
                    doc_type=doc_type,
                    title=doc_config["title"],
                    content=doc_content,
                    status="draft",
                    created_at=now,
                ),
                done=True,
            )

        for s in steps:
            if s.get("number") == request.step_number:
                s["status"] = "completed"
                break
        supabase_service.update_case(request.case_id, {"next_steps": steps})

        document = DocumentDTO(
            id=doc_id,
            case_id=request.case_id,
            doc_type=doc_type,
            title=doc_config["title"],
            content=doc_content,
            status="draft",
            created_at=now,
        )

        return ExecuteActionResponse(
            reply=f"I've drafted the {doc_config['title']} for you. You can review and edit it in the document panel on the right.",
            document=document,
            done=True,
        )

    async def chat(self, request: ChatRequestDTO) -> ChatResponseDTO:
        system_content = (
            f"{self.legal.system_prompt()}\n\n"
            f"You are helping the user with their legal case. "
            f"Be conversational and helpful. If the user wants to create or edit a legal document, "
            f"you can generate the document content."
        )

        if request.current_notice_draft:
            system_content += (
                f"\n\nCurrent document draft:\n{request.current_notice_draft}\n\n"
                f"If the user asks to edit the draft, return the updated full text in 'updated_notice'. "
                f"Otherwise 'updated_notice' should be empty."
            )

        system_content += (
            "\n\nRespond with JSON containing these keys:\n"
            '{"reply": "your conversational reply", '
            '"updated_notice": "full updated text or empty string", '
            '"document": {"doc_type": "demand_letter", "title": "...", "content": "..."} or null, '
            '"clarifying_questions": [], '
            '"action_buttons": []}'
            "\nNo markdown backticks. No extra text."
        )

        messages = [
            {"role": "system", "content": system_content},
        ]
        for h in request.history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": request.message})

        response = await self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=4000,
        )
        reply_text = response.choices[0].message.content or ""

        try:
            data = _extract_json(reply_text)
        except ValueError:
            data = {}

        doc_data = data.get("document")
        document = None
        if doc_data and doc_data.get("content"):
            document = DocumentDTO(
                id=_generate_doc_id(),
                case_id=request.case_id,
                doc_type=doc_data.get("doc_type", "legal_notice"),
                title=doc_data.get("title", "Legal Document"),
                content=doc_data.get("content", ""),
                status="draft",
                created_at=__import__("datetime").datetime.utcnow().isoformat(),
            )

        return ChatResponseDTO(
            reply=data.get("reply", reply_text),
            updated_notice=data.get("updated_notice", ""),
            updated_sections=data.get("updated_sections", []),
            clarifying_questions=[ClarifyingQuestion(**cq) for cq in data.get("clarifying_questions", [])],
            suggested_actions=[ActionButton(**ab) for ab in data.get("action_buttons", [])],
            document=document,
        )
