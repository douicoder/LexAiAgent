import asyncio
import json
import uuid
from datetime import datetime, timezone

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError

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
from app.interfaces.i_rag_service import IRagService

LLM_MODEL = settings.LLM_MODEL
FAST_MODEL = "gpt-4o"

# ── Document type definitions ───────────────────────────────────────────
# Only ask for personal details NOT already in the case description.
# The LLM receives the full case description and extracts subject, facts, and
# relief details automatically — no need to make users re-enter them.
DOCUMENT_TYPES = {
    "demand_letter": {
        "title": "Formal Demand Letter",
        "required_info": ["sender_name", "sender_address", "recipient_name", "recipient_address"],
        "info_labels": {"sender_name": "Your full name", "sender_address": "Your address", "recipient_name": "Recipient's full name", "recipient_address": "Recipient's address"},
    },
    "legal_notice": {
        "title": "Legal Notice",
        "required_info": ["sender_name", "sender_address", "recipient_name", "recipient_address"],
        "info_labels": {"sender_name": "Your full name", "sender_address": "Your address", "recipient_name": "Recipient's full name", "recipient_address": "Recipient's address"},
    },
    "court_filing": {
        "title": "Court Filing / Petition",
        "required_info": ["petitioner_name", "petitioner_address", "respondent_name", "respondent_address", "court_name"],
        "info_labels": {"petitioner_name": "Your full name (Petitioner)", "petitioner_address": "Your address", "respondent_name": "Respondent's full name", "respondent_address": "Respondent's address", "court_name": "Name of the court"},
    },
    "affidavit": {
        "title": "Affidavit",
        "required_info": ["deponent_name", "deponent_address"],
        "info_labels": {"deponent_name": "Your full name (Deponent)", "deponent_address": "Your address"},
    },
    "complaint": {
        "title": "Formal Complaint",
        "required_info": ["complainant_name", "complainant_address", "respondent_name"],
        "info_labels": {"complainant_name": "Your full name (Complainant)", "complainant_address": "Your address", "respondent_name": "Respondent's name"},
    },
    "agreement": {
        "title": "Legal Agreement",
        "required_info": ["party_a_name", "party_a_address", "party_b_name", "party_b_address"],
        "info_labels": {"party_a_name": "First Party name", "party_a_address": "First Party address", "party_b_name": "Second Party name", "party_b_address": "Second Party address"},
    },
}


def _extract_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Empty text, no JSON object found")

    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"' and not escaped:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i+1])
    raise ValueError("No valid JSON object found in text")


def _generate_doc_id() -> str:
    return str(uuid.uuid4())


class AgentService:
    def __init__(self, rag: IRagService):
        self.client = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.github.ai/inference",
        )
        self.rag = rag
        self.legal = LegalHelper()
        self.text = TextHelper()

    async def _call_llm(self, model: str, messages: list, max_tokens: int, max_retries: int = 1) -> str:
        timeout = httpx.Timeout(6.0, connect=4.0)
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                return response.choices[0].message.content.strip() or ""
            except (RateLimitError, APITimeoutError, APIConnectionError):
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                await asyncio.sleep(wait)
        return ""

    def _mock_analysis(self, description: str) -> AnalyzeResponseDTO:
        desc_lower = description.lower()
        if "landlord" in desc_lower or "tenant" in desc_lower or "deposit" in desc_lower or "rent" in desc_lower:
            case_type = "tenancy_dispute"
            legal_domain = "Landlord-Tenant"
            severity = "medium"
            summary = "This is a security deposit dispute between a tenant and landlord. The tenant has vacated the premises and the landlord is withholding the deposit without providing evidence of damage. The tenant has the rental agreement and payment records, which strengthens their position."
            ai_message = "I've analyzed your tenancy dispute. You have a strong case for recovering your security deposit, especially since you have the rental agreement and payment records. Let me walk you through the next steps."
            risk = "medium"
            readiness = 65
            evidence_have = ["Rental agreement / lease contract", "Bank transfer records for deposit payment", "Vacation handover proof or date records", "Communication records with landlord"]
            evidence_need = ["Written notice demanding deposit return (with proof of delivery)", "Photographs of apartment condition at move-out", "Witness statements if available", "Any repair estimates the landlord claims"]
            sections = [
                {"act": "Transfer of Property Act, 1882", "chapter": "", "section_number": "108", "section_title": "Rights and liabilities of lessor and lessee", "score": 0.92, "vector_score": 0.89, "bm25_score": 0.85, "excerpt": "In the absence of a contract or local usage to the contrary, the lessee shall allow the lessor and his agents to enter upon the property and inspect the condition thereof at all reasonable hours."},
                {"act": "Indian Contract Act, 1872", "chapter": "", "section_number": "73", "section_title": "Compensation for loss or damage caused by breach of contract", "score": 0.88, "vector_score": 0.86, "bm25_score": 0.82, "excerpt": "When a contract has been broken, the party who suffers by such breach is entitled to receive, from the party who has broken the contract, compensation for any loss or damage caused to him thereby, which naturally arose in the usual course of business from such breach."},
                {"act": "Code of Civil Procedure, 1908", "chapter": "", "section_number": "Order 37", "section_title": "Summary Procedure", "score": 0.76, "vector_score": 0.72, "bm25_score": 0.68, "excerpt": "Summary procedure applies to suits upon bills of exchange, hundies and promissory notes, and suits in which the plaintiff seeks only to recover a debt or liquidated demand in money."},
            ]
        elif "consumer" in desc_lower or "product" in desc_lower or "defective" in desc_lower or "service" in desc_lower:
            case_type = "consumer_dispute"
            legal_domain = "Consumer Protection"
            severity = "medium"
            summary = "This appears to be a consumer dispute regarding a product or service. Under the Consumer Protection Act, 2019, you have the right to seek redressal for defective goods or deficient services."
            ai_message = "I've analyzed your consumer complaint. You have options under the Consumer Protection Act to seek a resolution. Let me outline the steps you can take."
            risk = "low"
            readiness = 70
            evidence_have = ["Purchase receipt / invoice", "Warranty or guarantee card", "Photographs/videos of defect", "Communication with seller/provider"]
            evidence_need = ["Expert opinion on the defect", "Medical records (if personal injury)", "Cost estimates for repairs", "Copy of complaint to seller/provider"]
            sections = [
                {"act": "Consumer Protection Act, 2019", "chapter": "", "section_number": "2(7)", "section_title": "Definition of Consumer", "score": 0.95, "vector_score": 0.92, "bm25_score": 0.90, "excerpt": "Consumer means any person who buys any goods for a consideration which has been paid or promised or partly paid and partly promised, or under any system of deferred payment and includes any user of such goods other than the person who buys such goods for consideration paid or promised."},
                {"act": "Consumer Protection Act, 2019", "chapter": "", "section_number": "35", "section_title": "Filing of complaints before District Commission", "score": 0.91, "vector_score": 0.88, "bm25_score": 0.85, "excerpt": "A complaint may be filed with the District Commission by the consumer to whom such goods are sold or delivered or agreed to be sold or delivered or such services provided or agreed to be provided."},
            ]
        else:
            case_type = "other"
            legal_domain = "Civil"
            severity = "low"
            summary = "Your legal matter has been reviewed. Based on the information provided, here is an assessment of your situation and recommended course of action."
            ai_message = "I've reviewed your case. Here's my analysis and recommended steps to help you move forward."
            risk = "low"
            readiness = 45
            evidence_have = ["Relevant documents and records", "Any correspondence related to the matter"]
            evidence_need = ["Gather all related documents", "Document timeline of events", "Identify relevant legal provisions"]
            sections = []

        steps = [
            ActionStep(number=1, text="Send a formal legal notice to the opposing party", action_type="generate_document", action_config={"doc_type": "legal_notice", "title": "Legal Notice"}, status="pending"),
            ActionStep(number=2, text="Wait for response from the opposing party (up to 15 days)", action_type="wait", action_config={}, status="pending"),
            ActionStep(number=3, text="Collect and organize all evidence for potential legal proceedings", action_type="info_gathering", action_config={}, status="pending"),
            ActionStep(number=4, text="File a complaint with the appropriate authority if no response received", action_type="generate_document", action_config={"doc_type": "complaint", "title": "Formal Complaint"}, status="pending"),
        ]

        notice = f"LEGAL NOTICE\n\nTO:\n[Opponent's Name]\n[Opponent's Address]\n\nFROM:\n[Your Name]\n[Your Address]\n\nDate: {datetime.now(timezone.utc).strftime('%d %B %Y')}\n\nSUBJECT: Legal notice regarding {case_type.replace('_', ' ')}\n\nDear Sir/Madam,\n\nI, [Your Name], hereby serve this legal notice upon you through my authorized representative.\n\n{summary}\n\nYou are hereby called upon to:\n1. Provide a full and complete response to the matters raised herein within 15 days from the receipt of this notice;\n2. Refrain from any act that may prejudice the rights of the notice-sender;\n3. Preserve all documents and evidence related to the subject matter of this dispute.\n\nIn the event of your failure to comply with the above demands, I shall be constrained to initiate appropriate legal proceedings against you before the competent court of law, wherein you shall be held liable for all costs and expenses incurred.\n\nThis notice is issued without prejudice to any other rights and remedies available to me under the law.\n\nYours faithfully,\n\n[Your Name]\n[Signature]"

        return AnalyzeResponseDTO(
            case_type=case_type,
            severity=severity,
            legal_domain=legal_domain,
            relevant_sections=sections,
            legal_notice_draft=notice,
            summary=summary,
            next_steps=steps,
            reasoning_trace="[mock_analysis] API rate limited — using fallback analysis",
            clarifying_questions=[],
            action_buttons=[ActionButton(label="Generate Legal Notice", message="Generate the legal notice document", style="primary")],
            ai_message=ai_message,
            case_readiness_score=readiness,
            evidence_available=evidence_have,
            evidence_missing=evidence_need,
            risk_level=risk,
            recommended_actions=[
                f"Send a formal legal notice to the opposing party",
                f"Collect and preserve all evidence supporting your claim",
                f"Consult with a lawyer specializing in {legal_domain} law",
                f"File a complaint with the appropriate authority if the matter remains unresolved",
            ],
        )

    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        description = request.description
        if request.language == "hi":
            description = await self.text.translate_to_english(description)

        reasoning_trace = []

        try:
            # ── Round 0: Check for vagueness ───────────────────────────────────
            return await self._run_llm_analysis(description, reasoning_trace)
        except (RateLimitError, APITimeoutError, APIConnectionError):
            reasoning_trace.append("[mock_analysis] API unavailable — using fallback analysis")
            return self._mock_analysis(description)

    async def _run_llm_analysis(self, description: str, reasoning_trace: list) -> AnalyzeResponseDTO:
        vague_prompt = (
            f"Problem: {description}\n\n"
            f"Is this legal problem description too vague to provide "
            f"meaningful legal advice? If yes, generate up to 3 clarifying "
            f"questions that would help understand the situation better.\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{"is_vague": true/false, '
            f'"clarifying_questions": [{{"question": "your question here", '
            f'"key": "short_key_for_this_question"}}]}}'
            f"\nIf not vague, set clarifying_questions to an empty array."
        )
        vague_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": vague_prompt},
            ],
            max_tokens=1000,
        )
        try:
            vague_result = _extract_json(vague_text)
        except ValueError:
            vague_result = {"is_vague": False, "clarifying_questions": []}
        is_vague = vague_result.get("is_vague", False)
        vague_questions = vague_result.get("clarifying_questions", [])
        reasoning_trace.append(f"[check_vagueness] is_vague={is_vague} questions={len(vague_questions)}")

        # ── Round 1: Classify case ────────────────────────────────────────────
        classify_prompt = (
            f"Problem: {description}\n\n"
            f"Classify this legal problem into a JSON object:\n"
            f'{{"case_type": "tenancy_dispute|property_ownership|property_registration|consumer_dispute|employment_dispute|other", '
            f'"severity": "low|medium|high|urgent", '
            f'"legal_domain": "Landlord-Tenant|Consumer Protection|Employment|Property|Criminal|Family|Other", '
            f'"reasoning": "brief reason"}}'
        )

        classify_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
            ],
            max_tokens=1000,
        )
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

        search_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
                {"role": "assistant", "content": classify_text},
                {"role": "user", "content": search_prompt},
            ],
            max_tokens=1000,
        )
        search_args = _extract_json(search_text)
        query = search_args.get("query", description)

        law_sections = await self.rag.search(query=query, top_k=5)
        reasoning_trace.append(f"[search_law: '{query}'] -> {len(law_sections)} results")

        # ── Round 3: Generate full analysis ───────────────────────────────────
        steps_prompt = (
            f"Problem: {description}\n\n"
            f"Classification: {json.dumps(classification, indent=2)}\n\n"
            f"Relevant laws:\n{json.dumps(law_sections, indent=2, default=str)}\n\n"
            f"Generate a complete legal analysis as JSON. Prefix with 'FINAL_JSON:' then the JSON. No markdown.\n\n"
            f"Keys:\n"
            f'  "ai_message" — warm conversational message (2-3 sentences)\n'
            f'  "summary" — case summary and recommended approach (2-3 sentences)\n'
            f'  "steps" — array of {{number, text, action_type (generate_document|wait|info_gathering), action_config: {{doc_type, title}}}}\n'
            f'  "legal_notice_draft" — plain text string (NOT a JSON object). A complete formal legal notice with TO, FROM, subject, body, legal grounds, demand clause, and signature. Use Indian legal format.\n'
            f'  "case_readiness_score" — integer 0-100\n'
            f'  "evidence_available" — array of strings (evidence user likely has)\n'
            f'  "evidence_missing" — array of strings (evidence user still needs)\n'
            f'  "risk_level" — "low"|"medium"|"high"\n'
            f'  "recommended_actions" — array of plain text action recommendations\n'
        )

        final_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": steps_prompt},
            ],
            max_tokens=8000,
        )

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
            for q in (vague_questions + final_data.get("clarifying_questions", []))
        ]

        action_buttons_items = [
            ActionButton(label=ab.get("label", ""), message=ab.get("message", ""), style=ab.get("style", "default"))
            for ab in final_data.get("action_buttons", [])
        ]

        return AnalyzeResponseDTO(
            case_type=classification.get("case_type", "other"),
            severity=classification.get("severity", "medium"),
            legal_domain=classification.get("legal_domain", ""),
            relevant_sections=law_sections,
            legal_notice_draft=final_data.get("legal_notice_draft", ""),
            summary=final_data.get("summary", ""),
            next_steps=action_steps,
            reasoning_trace="\n".join(reasoning_trace),
            clarifying_questions=clarifying_questions,
            action_buttons=action_buttons_items,
            ai_message=final_data.get("ai_message", f"I've analyzed your case. Here's a step-by-step plan to help you resolve this matter."),
            case_readiness_score=final_data.get("case_readiness_score", 0),
            evidence_available=final_data.get("evidence_available", []),
            evidence_missing=final_data.get("evidence_missing", []),
            risk_level=final_data.get("risk_level", "medium"),
            recommended_actions=final_data.get("recommended_actions", []),
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
            f"Case description (extract subject, facts, and relief from here):\n{description}\n"
            f"Case type: {case_type} ({severity})\n\n"
            f"Relevant law sections:\n{json.dumps(relevant_sections, indent=2, default=str)}\n\n"
            f"Personal details provided by the user:\n{json.dumps(request.collected_info, indent=2)}\n\n"
            f"Using the case description for the content and the personal details above for names/addresses, "
            f"generate the complete legal document in proper legal format.\n"
            f"Do NOT ask the user to re-explain their issue — everything needed is in the case description "
            f"and personal details above.\n"
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
        now = datetime.now(timezone.utc).isoformat()

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
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        return ChatResponseDTO(
            reply=data.get("reply", reply_text),
            updated_notice=data.get("updated_notice", ""),
            updated_sections=data.get("updated_sections", []),
            clarifying_questions=[ClarifyingQuestion(**cq) for cq in data.get("clarifying_questions", [])],
            suggested_actions=[ActionButton(**ab) for ab in data.get("action_buttons", [])],
            document=document,
        )
